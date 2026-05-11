"""
撮合引擎核心逻辑

撮合规则：
  - 价格优先：买单价高者优先，卖单价低者优先
  - 时间优先：同价格按下单时间 FIFO
  - 成交价 = 挂单方（Maker）的价格

支持订单类型：
  LIMIT + GTC  — 限价挂单，未成交部分留在订单簿
  LIMIT + GTX  — Post Only，若会立即成交则拒绝
  LIMIT + IOC  — 立即成交，剩余撤单
  LIMIT + FOK  — 必须完全成交，否则全部撤单
  MARKET       — 市价单，逐档吃单
"""

import time
from collections.abc import Callable

from .order import Order, OrderSide, OrderStatus, OrderType, TimeInForce, QTY_EPSILON
from .order_book import OrderBook
from .trade import Trade


class MatchingEngine:

    def __init__(self, symbol: str,
                 on_trade: Callable[[Trade], None] | None = None):
        self.symbol = symbol
        self.order_book = OrderBook(symbol)
        self._on_trade = on_trade    # 成交回调，解耦通知逻辑
        self._trade_counter = 0

    # ─────────────────────────────────────────────────────
    # 对外接口
    # ─────────────────────────────────────────────────────

    def submit(self, order: Order) -> list[Trade]:
        """
        提交订单，返回本次撮合产生的成交列表。
        订单状态在函数内部更新。
        """
        if order.order_type == OrderType.MARKET:
            return self._match_market(order)
        else:
            return self._match_limit(order)

    def cancel(self, order: Order) -> bool:
        """撤销订单，返回是否成功"""
        if not order.is_active:
            return False
        removed = self.order_book.remove_order(order)
        if removed:
            order.status = OrderStatus.CANCELED
        return removed

    # ─────────────────────────────────────────────────────
    # 限价单撮合
    # ─────────────────────────────────────────────────────

    def _match_limit(self, order: Order) -> list[Trade]:
        # GTX：若会立即成交则拒绝
        if order.time_in_force == TimeInForce.GTX:
            if self._would_match_immediately(order):
                order.status = OrderStatus.REJECTED
                return []

        # FOK：预检查能否完全成交
        if order.time_in_force == TimeInForce.FOK:
            if not self._can_fill_completely(order):
                order.status = OrderStatus.REJECTED
                return []

        trades = self._do_match(order)

        # IOC / FOK：剩余撤单
        # IOC：剩余撤单（正常路径）
        # FOK：理论上不会走到这里（预检已保证完全成交），防御性处理
        if order.time_in_force in (TimeInForce.IOC, TimeInForce.FOK):
            if order.is_active:
                order.status = OrderStatus.CANCELED
            return trades

        # GTC / GTX：剩余挂入订单簿
        if order.is_active:
            self.order_book.add_order(order)

        return trades

    # ─────────────────────────────────────────────────────
    # 市价单撮合
    # ─────────────────────────────────────────────────────

    def _match_market(self, order: Order) -> list[Trade]:
        trades = self._do_match(order)
        # 市价单剩余数量直接取消（流动性不足）
        if order.is_active:
            order.status = OrderStatus.CANCELED
        return trades

    # ─────────────────────────────────────────────────────
    # 核心撮合循环
    # ─────────────────────────────────────────────────────

    def _do_match(self, order: Order) -> list[Trade]:
        trades = []

        while order.remaining_qty > QTY_EPSILON:
            # 取对手方最优订单
            if order.side == OrderSide.BUY:
                best = self.order_book.peek_best_ask()
                if best is None:
                    break
                # 限价单：买单价 >= 卖单价才能成交
                if order.price is not None and order.price < best.price:
                    break
                maker = self.order_book.pop_best_ask()
            else:
                best = self.order_book.peek_best_bid()
                if best is None:
                    break
                # 限价单：卖单价 <= 买单价才能成交
                if order.price is not None and order.price > best.price:
                    break
                maker = self.order_book.pop_best_bid()

            # 防御性检查：防止竞态条件下订单簿为空
            if maker is None:
                break

            # 成交数量 = 双方剩余数量的最小值
            match_qty = min(order.remaining_qty, maker.remaining_qty)
            match_price = maker.price   # 成交价 = 挂单方价格

            # 生成成交记录（时间戳在 _make_trade 内部取，每笔独立）
            trade = self._make_trade(order, maker, match_price, match_qty)
            trades.append(trade)

            # 更新双方成交数量
            order.fill(match_qty)
            maker.fill(match_qty)

            # maker 未完全成交，放回队首保持时间优先
            if maker.is_active:
                self.order_book.put_back(maker)

            # 触发回调
            if self._on_trade:
                self._on_trade(trade)

        return trades

    # ─────────────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────────────

    def _would_match_immediately(self, order: Order) -> bool:
        """判断限价单提交时是否会立即成交（用于 GTX 检查）"""
        if order.side == OrderSide.BUY:
            best_ask = self.order_book.best_ask()
            return best_ask is not None and order.price >= best_ask
        else:
            best_bid = self.order_book.best_bid()
            return best_bid is not None and order.price <= best_bid

    def _can_fill_completely(self, order: Order) -> bool:
        """判断 FOK 订单能否完全成交"""
        remaining = order.remaining_qty

        if order.side == OrderSide.BUY:
            for _, level in self.order_book.iter_asks_up_to(order.price):
                for o in level:
                    remaining -= o.remaining_qty
                    if remaining <= QTY_EPSILON:
                        return True
        else:
            for _, level in self.order_book.iter_bids_down_to(order.price):
                for o in level:
                    remaining -= o.remaining_qty
                    if remaining <= QTY_EPSILON:
                        return True

        return False

    def _make_trade(self, taker: Order, maker: Order,
                    price: float, qty: float) -> Trade:
        self._trade_counter += 1
        is_buyer_maker = (maker.side == OrderSide.BUY)
        return Trade(
            trade_id=f"T{self._trade_counter:08d}",
            symbol=self.symbol,
            price=price,
            quantity=qty,
            buyer_order_id=maker.order_id if is_buyer_maker else taker.order_id,
            seller_order_id=taker.order_id if is_buyer_maker else maker.order_id,
            timestamp=int(time.time() * 1000),
            is_buyer_maker=is_buyer_maker,
        )
