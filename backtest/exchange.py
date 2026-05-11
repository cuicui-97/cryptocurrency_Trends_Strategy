"""
回测交易所模拟器

对外暴露标准 BaseTrader 接口（下单、撤单、查单），
内部用撮合引擎模拟真实交易所行为，策略完全不感知撮合细节。

撮合原理（单引擎，时间优先）：
  市场挂单（来自订单簿快照，MKT_ 前缀）先于策略挂单进入订单簿，
  aggTrade 来了提交 IOC 单，按价格+时间顺序撮合：
    市场单 t=0 挂 → 先成交
    策略单 t=1 挂 → 市场深度消耗完后才轮到

供 BacktestDataFetcher 调用的两个方法：
  sync_order_book(snapshot)          — 增量同步市场深度
  on_agg_trade(price, qty, maker)    — 驱动撮合
"""

import uuid

from config.base import TradingConfig
from config import STRATEGY_CONFIG
from core.exchange import Exchange
from core.logger import make_logger
from matching.matcher import Matcher
from matching.core.trade import Trade

_MKT_PREFIX = "MKT_"   # 市场挂单前缀（来自订单簿快照）
_AGG_PREFIX = "AGG_"   # aggTrade IOC 单前缀（模拟市场 taker）


class BacktestExchange(Exchange):

    def __init__(self, symbol: str = TradingConfig().symbol,
                 log_file: str = STRATEGY_CONFIG.log_file):
        super().__init__()
        self.symbol = symbol
        self.logger = make_logger(__name__, log_file)
        self._engine = Matcher(on_trade=self._on_trade)
        # 当前市场挂单：price → order_id（买盘/卖盘分开）
        self._mkt_bids: dict[float, str] = {}
        self._mkt_asks: dict[float, str] = {}

    # ─────────────────────────────────────────────────────
    # 供 BacktestDataFetcher 调用
    # ─────────────────────────────────────────────────────

    def sync_order_book(self, snapshot: dict) -> None:
        """
        增量同步订单簿快照到撮合引擎。
        只更新有变化的档位，保留策略挂单不受影响。

        snapshot: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
        """
        new_bids = {float(p): float(q) for p, q in snapshot.get("bids", []) if float(q) > 0}
        new_asks = {float(p): float(q) for p, q in snapshot.get("asks", []) if float(q) > 0}
        self._sync_side(new_bids, self._mkt_bids, "BUY")
        self._sync_side(new_asks, self._mkt_asks, "SELL")

    def on_agg_trade(self, price: float, qty: float, is_buyer_maker: bool) -> None:
        """
        用 aggTrade 驱动撮合。提交 IOC 限价单，触发订单簿里所有符合条件的挂单。用IOC模拟市价单。
        市场单因先挂而先成交，策略单排在后面。

        is_buyer_maker=True：买方是挂单方，卖方主动吃单
          → 提交 IOC 卖单，吃买盘 >= price 的挂单
        is_buyer_maker=False：卖方是挂单方，买方主动吃单
          → 提交 IOC 买单，吃卖盘 <= price 的挂单
        """
        taker_side = "SELL" if is_buyer_maker else "BUY"
        self._engine.place_order(
            self.symbol, taker_side, "LIMIT", qty,
            price=price, time_in_force="IOC",
            order_id=f"{_AGG_PREFIX}{uuid.uuid4()}",
        )

    # ─────────────────────────────────────────────────────
    # BaseTrader 标准接口
    # ─────────────────────────────────────────────────────

    async def connect_and_login(self) -> None:
        self.logger.info("[回测] BacktestExchange 初始化完成")

    async def submit_market_order(self, symbol: str, side: str,
                                  size: float) -> str | None:
        """
        市价单：以当前最优价提交 IOC 限价单，立即成交或取消。
        """
        ob = self._engine.get_order_book(symbol)
        ref_price = ob.get("best_ask") if side.upper() == "BUY" else ob.get("best_bid")

        if ref_price is None:
            self.logger.warning(f"[回测] 市价单无对手方，跳过")
            return None

        result = self._engine.place_order(
            symbol, side.upper(), "LIMIT", size,
            price=ref_price, time_in_force="IOC",
        )
        if "error" in result:
            self.logger.error(f"[回测] 市价单失败: {result['error']}")
            return None

        oid = result["order_id"]
        self.logger.info(
            f"[回测] 市价单 {side.upper()} size={size} ref={ref_price} "
            f"→ {oid} {result['status']}"
        )
        # 无论成交还是取消，都通知等待方
        self.notify_fill(oid)
        return oid

    async def submit_limit_order(self, symbol: str, side: str,
                                 price: float, size: float,
                                 reduce_only: bool = False,
                                 post_only: bool = False) -> str | None:
        """
        限价单：GTC 挂入订单簿，等待 aggTrade 触发成交。
        回测里忽略 post_only（GTX 在有对手方时会被拒，不适合回测）。
        """
        result = self._engine.place_order(
            symbol, side.upper(), "LIMIT", size,
            price=price, time_in_force="GTC",
        )
        if "error" in result:
            self.logger.error(f"[回测] 限价单失败: {result['error']}")
            return None

        oid = result["order_id"]
        self.logger.info(
            f"[回测] 限价单 {side.upper()} price={price} size={size} "
            f"→ {oid} {result['status']}"
        )
        # 若提交时已立即成交（订单簿里恰好有对手方），通知等待方
        if result["status"] == "FILLED":
            self.notify_fill(oid)
        return oid

    async def get_order_status(self, symbol: str, order_id: str) -> str | None:
        order = self._engine.get_order(order_id)
        return order["status"] if order else "CANCELED"

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        self._engine.cancel_order(order_id)
        self.logger.info(f"[回测] 撤单 {order_id}")
        self.notify_fill(order_id)

    # ─────────────────────────────────────────────────────
    # 内部
    # ─────────────────────────────────────────────────────

    def _on_trade(self, trade: Trade) -> None:
        """撮合引擎成交回调，只通知策略挂单"""
        for oid in (trade.buyer_order_id, trade.seller_order_id):
            if not oid.startswith(_MKT_PREFIX) and not oid.startswith(_AGG_PREFIX):
                self.notify_fill(oid)

    def _sync_side(self, new_levels: dict[float, float],
                   current: dict[float, str], side: str) -> None:
        """增量同步一侧挂单：撤消失档位，更新数量变化档位"""
        for price in set(current) - set(new_levels):
            self._engine.cancel_order(current.pop(price))

        for price, qty in new_levels.items():
            oid = current.get(price)
            if oid is not None:
                order = self._engine.get_order(oid)
                if order and abs(order["remaining_qty"] - qty) < 1e-8:
                    continue  # 数量没变，不动
                self._engine.cancel_order(oid)

            new_oid = f"{_MKT_PREFIX}{side.lower()}_{price}"
            result = self._engine.place_order(
                self.symbol, side, "LIMIT", qty,
                price=price, time_in_force="GTC", order_id=new_oid,
            )
            if "error" not in result:
                current[price] = new_oid
