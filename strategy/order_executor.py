"""
订单执行器

负责完整的交易生命周期：
  1. 提交开仓限价单，等待成交
  2. 成交后同时挂止盈单和止损单
  3. 轮询哪笔先成交，撤掉另一笔
  4. 记录盈亏
"""

import asyncio

import config
from core.logger import make_logger
from exchange.binance.trader import BinanceTrader
from strategy.pnl_tracker import PnlTracker

POLL_INTERVAL = 2


class OrderExecutor:

    def __init__(self, trader: BinanceTrader, pnl_tracker: PnlTracker):
        self.trader = trader
        self.pnl_tracker = pnl_tracker
        self.logger = make_logger(__name__, config.TRADER_LOG_FILE)
        self._in_position = False   # 是否有持仓，True 时拒绝新开仓

    def execute(self, symbol: str, side: str, price: float, size: float) -> None:
        """提交开仓单，有持仓时直接跳过"""
        if self._in_position:
            self.logger.info(f"[开仓] 当前有持仓，跳过信号 side={side} price={price}")
            return
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
        # 市价单直接成交，不需要等待和撤单
        order_id = await self.trader.submit_market_order(symbol, side, size)
        if order_id is None:
            return

        self.logger.info(f"[开仓] 市价单成交 orderId={order_id} side={side}")
        self._in_position = True
        await self._close(symbol, side, price, size)
        self._in_position = False
        self.logger.info("[开仓] 持仓已清空，可以开新仓")

    # ─────────────────────────────────────────────────────
    # 平仓（止盈 + 止损）
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
            self.logger.error("[平仓] 挂单失败，撤销已提交的单")
            if tp_id:
                await self.trader.cancel_order(symbol, tp_id)
            if sl_id:
                await self.trader.cancel_order(symbol, sl_id)
            return

        self.logger.info(f"[平仓] 止盈单={tp_id} 止损单={sl_id}，开始轮询")

        tp_task = asyncio.create_task(
            self._poll_until_filled(symbol, tp_id, "止盈单"), name="止盈轮询"
        )
        sl_task = asyncio.create_task(
            self._poll_until_filled(symbol, sl_id, "止损单"), name="止损轮询"
        )

        done, pending = await asyncio.wait(
            [tp_task, sl_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        finished = done.pop()
        if finished is tp_task:
            self.pnl_tracker.record(side, entry_price, tp_price, size, "take_profit")
            await self.trader.cancel_order(symbol, sl_id)
        else:
            self.pnl_tracker.record(side, entry_price, sl_price, size, "stop_loss")
            await self.trader.cancel_order(symbol, tp_id)

        self.logger.info(f"[统计] {self.pnl_tracker.summary()}")

    # ─────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────

    async def _place_order(self, symbol: str, side: str, price: float,
                           size: float, label: str,
                           post_only: bool = True) -> int | None:
        """
        post_only=True  → GTX，只做 Maker（止盈用）
        post_only=False → GTC，允许 Taker 成交（止损用）
        """
        self.logger.info(f"[平仓] 挂{label}: {side.upper()} price={price} {'GTX' if post_only else 'GTC'}")
        return await self.trader.submit_limit_order(
            symbol, side, price, size,
            reduce_only=True,
            post_only=post_only
        )

    async def _poll_until_filled(self, symbol: str, order_id: int,
                                 label: str) -> str | None:
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            status = await self.trader.get_order_status(symbol, order_id)
            self.logger.info(f"[平仓] {label} {order_id} 状态: {status}")
            if status in ("FILLED", "CANCELED", "EXPIRED"):
                return status

    def _calc_take_profit_price(self, side: str, entry_price: float) -> float:
        if side == "buy":
            return round(entry_price * (1 + config.SPREAD), 1)
        else:
            return round(entry_price * (1 - config.SPREAD), 1)

    def _calc_stop_loss_price(self, side: str, entry_price: float) -> float:
        if side == "buy":
            return round(entry_price * (1 - config.STOP_LOSS), 1)
        else:
            return round(entry_price * (1 + config.STOP_LOSS), 1)

    def _on_task_done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            self.logger.error(f"[执行器] 后台任务异常: {task.exception()}")
