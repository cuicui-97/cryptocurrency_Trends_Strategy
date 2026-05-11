"""
撮合引擎入口

对外暴露统一接口，隐藏内部实现细节。
支持多交易对，每个交易对维护独立的 MatchingEngine。
"""

import time
import uuid
from collections.abc import Callable

from matching.core.engine import MatchingEngine
from .core.order import Order, OrderSide, OrderStatus, OrderType, TimeInForce
from .core.trade import Trade


class Matcher:

    def __init__(self, on_trade: Callable[[Trade], None] | None = None):
        self._engines: dict[str, MatchingEngine] = {}
        self._orders: dict[str, Order] = {}     # order_id → Order
        self._trades: list[Trade] = []           # 全局成交记录
        self._on_trade = on_trade

    def _get_or_create(self, symbol: str) -> MatchingEngine:
        if symbol not in self._engines:
            self._engines[symbol] = MatchingEngine(
                symbol=symbol,
                on_trade=self._record_trade
            )
        return self._engines[symbol]

    def _record_trade(self, trade: Trade) -> None:
        """内部成交记录 + 转发外部回调"""
        self._trades.append(trade)
        if self._on_trade:
            self._on_trade(trade)

    # ─────────────────────────────────────────────────────
    # 下单
    # ─────────────────────────────────────────────────────

    def place_order(self,
                    symbol: str,
                    side: str,
                    order_type: str,
                    quantity: float,
                    price: float | None = None,
                    time_in_force: str = "GTC",
                    order_id: str | None = None,
                    timestamp: int | None = None) -> dict:
        """
        提交订单。

        参数：
          symbol        — 交易对，如 'BTCUSDT'
          side          — 'BUY' 或 'SELL'
          order_type    — 'LIMIT' 或 'MARKET'
          quantity      — 下单数量
          price         — 限价单价格，市价单不传
          time_in_force — 'GTC' / 'GTX' / 'IOC' / 'FOK'
          order_id      — 自定义订单 ID，不传则自动生成
          timestamp     — 时间戳（毫秒），不传则用当前时间

        返回：
          {order_id, status, filled_qty, remaining_qty, trades: [...]}
        """
        try:
            order = Order(
                order_id=order_id or str(uuid.uuid4()),
                symbol=symbol,
                side=OrderSide[side.upper()],
                order_type=OrderType[order_type.upper()],
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce[time_in_force.upper()],
                created_at=timestamp or int(time.time() * 1000),
            )
        except KeyError as e:
            return {"error": f"无效参数: {e}"}

        self._orders[order.order_id] = order
        engine = self._get_or_create(symbol)
        trades = engine.submit(order)

        return {
            "order_id": order.order_id,
            "status": order.status.value,
            "filled_qty": order.filled_qty,
            "remaining_qty": order.remaining_qty,
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "price": t.price,
                    "quantity": t.quantity,
                    "is_buyer_maker": t.is_buyer_maker,
                }
                for t in trades
            ],
        }

    # ─────────────────────────────────────────────────────
    # 撤单
    # ─────────────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> dict:
        """撤销订单"""
        order = self._orders.get(order_id)
        if order is None:
            return {"success": False, "reason": "order not found"}

        engine = self._get_or_create(order.symbol)
        success = engine.cancel(order)
        return {
            "success": success,
            "order_id": order_id,
            "status": order.status.value,
        }

    # ─────────────────────────────────────────────────────
    # 查询
    # ─────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> dict | None:
        """查询订单状态"""
        order = self._orders.get(order_id)
        if order is None:
            return None
        return {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "price": order.price,
            "quantity": order.quantity,
            "filled_qty": order.filled_qty,
            "remaining_qty": order.remaining_qty,
            "status": order.status.value,
            "created_at": order.created_at,
        }

    def get_order_book(self, symbol: str, depth: int = 20) -> dict:
        """获取订单簿快照"""
        engine = self._get_or_create(symbol)
        return engine.order_book.snapshot(depth)

    def get_trades(self, symbol: str | None = None) -> list[dict]:
        """获取成交记录，不传 symbol 则返回全部"""
        trades = (
            [t for t in self._trades if t.symbol == symbol]
            if symbol else self._trades
        )
        return [
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "price": t.price,
                "quantity": t.quantity,
                "buyer_order_id": t.buyer_order_id,
                "seller_order_id": t.seller_order_id,
                "timestamp": t.timestamp,
                "is_buyer_maker": t.is_buyer_maker,
            }
            for t in trades
        ]
