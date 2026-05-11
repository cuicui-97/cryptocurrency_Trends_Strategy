"""
订单执行器

负责完整的交易生命周期：
  1. 提交市价开仓单，等待成交通知
  2. 成交后同时挂止盈单和止损单
  3. 等待哪笔先成交（事件驱动，不轮询），撤掉另一笔
  4. 记录盈亏

成交通知机制：
  - 回测模式：BacktestTrader 在撮合引擎 on_trade 回调里调用 trader.notify_fill()
  - 模拟盘模式：BinanceExchange 轮询到成交后调用 notify_fill()
  两种模式对 OrderExecutor 透明，统一通过 trader.wait_for_fill() 等待。
"""

import asyncio

from config import STRATEGY_CONFIG
from core.exchange import Exchange
from core.logger import make_logger
from strategy.pnl_tracker import PnlTracker


class OrderExecutor:

    def __init__(self, exchange: Exchange, pnl_tracker: PnlTracker):
        self.exchange = exchange
        self.pnl_tracker = pnl_tracker
        self.logger = make_logger(__name__, STRATEGY_CONFIG.TRADER_LOG_FILE)
        self._in_position = False

    def execute(self, symbol: str, side: str, price: float, size: float) -> None:
        """提交开仓单，有持仓时直接跳过"""
        if self._in_position:
            self.logger.info(f"[开仓] 当前有持仓，跳过信号 side={side} price={price}")
            return
        # 提前设置，防止 create_task 到 _open 被调度之间的时间窗口重复开仓
        self._in_position = True
        task = asyncio.create_task(
            self._open(symbol, side, price, size),
            name=f"开仓-{side}-{price}"
        )
        task.add_done_callback(self._on_task_done)

    # ─────────────────────────────────────────────────────
    # 开仓
    # ─────────────────────────────────────────────────────

    async def _open(self, symbol: str, side: str,
                    price: float, size: float) -> None:
        order_id = await self.exchange.submit_market_order(symbol, side, size)
        if order_id is None:
            self._in_position = False  # 开仓失败，释放锁
            return

        self.logger.info(f"[开仓] 市价单已提交 orderId={order_id} side={side}")

        # 等待市价单成交通知（回测：撮合引擎回调；模拟盘：轮询触发）
        await self.exchange.wait_for_fill(order_id)
        self.logger.info(f"[开仓] 市价单成交 orderId={order_id}")

        await self._close(symbol, side, price, size)
        self._in_position = False
        self.logger.info("[开仓] 持仓已清空，可以开新仓")

    # ─────────────────────────────────────────────────────
    # 平仓（止盈 + 止损竞争）
    # ─────────────────────────────────────────────────────

    async def _close(self, symbol: str, side: str,
                     entry_price: float, size: float) -> None:
        tp_price = self._calc_take_profit_price(side, entry_price)
        sl_price = self._calc_stop_loss_price(side, entry_price)
        close_side = "sell" if side == "buy" else "buy"

        self.logger.info(
            f"[平仓] side={side} entry={entry_price} "
            f"止盈={tp_price} 止损={sl_price}"
        )

        tp_id, sl_id = await asyncio.gather(
            self._place_order(symbol, close_side, tp_price, size, "止盈单", post_only=True),
            self._place_order(symbol, close_side, sl_price, size, "止损单", post_only=False),
        )

        if tp_id is None or sl_id is None:
            # 任意一个挂单失败，撤掉另一个，市价立即平仓
            reason = "止盈单 GTX 被拒（价格已到位）" if tp_id is None else "止损单挂单失败"
            self.logger.warning(f"[平仓] {reason}，市价强制平仓")
            if tp_id:
                await self.exchange.cancel_order(symbol, tp_id)
            if sl_id:
                await self.exchange.cancel_order(symbol, sl_id)
            mkt_id = await self.exchange.submit_market_order(symbol, close_side, size)
            if mkt_id:
                await self.exchange.wait_for_fill(mkt_id)
            # 止盈单被拒说明价格已到止盈位，记录止盈；否则记录止损
            result = "take_profit" if tp_id is None else "stop_loss"
            exit_price = tp_price if tp_id is None else sl_price
            self.pnl_tracker.record(side, entry_price, exit_price, size, result)
            self.logger.info(f"[统计] {self.pnl_tracker.summary()}")
            return

        # 正常路径：止盈止损都挂成功，等哪个先触发
        self.logger.info(f"[平仓] 止盈单={tp_id} 止损单={sl_id}，等待成交")

        tp_task = asyncio.create_task(
            self.exchange.wait_for_fill(tp_id), name="等待止盈"
        )
        sl_task = asyncio.create_task(
            self.exchange.wait_for_fill(sl_id), name="等待止损"
        )

        done, pending = await asyncio.wait(
            [tp_task, sl_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        finished = done.pop()
        if finished is tp_task:
            self.pnl_tracker.record(side, entry_price, tp_price, size, "take_profit")
            await self.exchange.cancel_order(symbol, sl_id)
        else:
            self.pnl_tracker.record(side, entry_price, sl_price, size, "stop_loss")
            await self.exchange.cancel_order(symbol, tp_id)

        self.logger.info(f"[统计] {self.pnl_tracker.summary()}")

    # ─────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────

    async def _place_order(self, symbol: str, side: str, price: float,
                           size: float, label: str,
                           post_only: bool = True) -> str | None:
        self.logger.info(
            f"[平仓] 挂{label}: {side.upper()} price={price} "
            f"{'GTX' if post_only else 'GTC'}"
        )
        return await self.exchange.submit_limit_order(
            symbol, side, price, size,
            reduce_only=True,
            post_only=post_only,
        )

    def _calc_take_profit_price(self, side: str, entry_price: float) -> float:
        if side == "buy":
            return round(entry_price * (1 + STRATEGY_CONFIG.SPREAD), 1)
        else:
            return round(entry_price * (1 - STRATEGY_CONFIG.SPREAD), 1)

    def _calc_stop_loss_price(self, side: str, entry_price: float) -> float:
        if side == "buy":
            return round(entry_price * (1 - STRATEGY_CONFIG.STOP_LOSS), 1)
        else:
            return round(entry_price * (1 + STRATEGY_CONFIG.STOP_LOSS), 1)

    def _on_task_done(self, task: asyncio.Task) -> None:
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                self.logger.error(f"[执行器] 后台任务异常: {exc}")
