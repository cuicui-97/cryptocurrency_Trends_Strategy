"""
订单簿

买卖盘各自用 SortedDict 维护，每个价格档位用 deque 实现 FIFO 时间优先。

买盘（bids）：价格降序（key = -price）
卖盘（asks）：价格升序（key = price）

时间复杂度：
  插入/删除：O(log n)
  取最优价：O(1)
"""

from collections import deque
from collections.abc import Iterator

from sortedcontainers import SortedDict

from .order import Order, OrderSide


class OrderBook:

    def __init__(self, symbol: str):
        self.symbol = symbol
        # 买盘：key = -price（负数实现降序，最优买价排最前）
        self._bids: SortedDict[float, deque[Order]] = SortedDict()
        # 卖盘：key = price（升序，最优卖价排最前）
        self._asks: SortedDict[float, deque[Order]] = SortedDict()

    # ─────────────────────────────────────────────────────
    # 订单管理
    # ─────────────────────────────────────────────────────

    def add_order(self, order: Order) -> None:
        """将订单加入订单簿（队尾，时间优先）"""
        if order.side == OrderSide.BUY:
            key = -order.price
            if key not in self._bids:
                self._bids[key] = deque()
            self._bids[key].append(order)
        else:
            key = order.price
            if key not in self._asks:
                self._asks[key] = deque()
            self._asks[key].append(order)

    def remove_order(self, order: Order) -> bool:
        """从订单簿中移除指定订单，返回是否成功"""
        if order.side == OrderSide.BUY:
            key = -order.price
            book = self._bids
        else:
            key = order.price
            book = self._asks

        if key not in book:
            return False

        level = book[key]
        try:
            level.remove(order)
        except ValueError:
            return False

        if not level:
            del book[key]
        return True

    def put_back(self, order: Order) -> None:
        """将部分成交的 maker 放回队首（保持时间优先）"""
        if order.side == OrderSide.BUY:
            key = -order.price
            if key not in self._bids:
                self._bids[key] = deque()
            self._bids[key].appendleft(order)
        else:
            key = order.price
            if key not in self._asks:
                self._asks[key] = deque()
            self._asks[key].appendleft(order)

    # ─────────────────────────────────────────────────────
    # 最优价格
    # ─────────────────────────────────────────────────────

    def best_bid(self) -> float | None:
        """最优买价（最高买价）"""
        if not self._bids:
            return None
        return -self._bids.keys()[0]

    def best_ask(self) -> float | None:
        """最优卖价（最低卖价）"""
        if not self._asks:
            return None
        return self._asks.keys()[0]

    def spread(self) -> float | None:
        """买卖价差"""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return round(ask - bid, 8)

    def mid_price(self) -> float | None:
        """中间价"""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return round((bid + ask) / 2, 8)

    # ─────────────────────────────────────────────────────
    # 撮合用：取对手方队首订单
    # ─────────────────────────────────────────────────────

    def pop_best_bid(self) -> Order | None:
        """取出最优买价队首订单（成交时调用）"""
        if not self._bids:
            return None
        key, level = self._bids.peekitem(0)
        order = level.popleft()
        if not level:
            del self._bids[key]
        return order

    def pop_best_ask(self) -> Order | None:
        """取出最优卖价队首订单（成交时调用）"""
        if not self._asks:
            return None
        key, level = self._asks.peekitem(0)
        order = level.popleft()
        if not level:
            del self._asks[key]
        return order

    def peek_best_bid(self) -> Order | None:
        """查看最优买价队首订单（不取出）"""
        if not self._bids:
            return None
        return self._bids.peekitem(0)[1][0]

    def peek_best_ask(self) -> Order | None:
        """查看最优卖价队首订单（不取出）"""
        if not self._asks:
            return None
        return self._asks.peekitem(0)[1][0]

    # ─────────────────────────────────────────────────────
    # 档位迭代（供撮合引擎使用，避免访问私有属性）
    # ─────────────────────────────────────────────────────

    def iter_asks_up_to(self, max_price: float | None) -> Iterator[tuple[float, deque[Order]]]:
        """从最优卖价开始，迭代价格 <= max_price 的每档 (price, deque)"""
        for key, level in self._asks.items():
            if max_price is not None and key > max_price:
                break
            yield key, level

    def iter_bids_down_to(self, min_price: float | None) -> Iterator[tuple[float, deque[Order]]]:
        """从最优买价开始，迭代价格 >= min_price 的每档 (price, deque)"""
        for key, level in self._bids.items():
            price = -key
            if min_price is not None and price < min_price:
                break
            yield price, level

    # ─────────────────────────────────────────────────────
    # 快照
    # ─────────────────────────────────────────────────────

    def snapshot(self, depth: int = 20) -> dict:
        """返回订单簿快照，最多 depth 档"""
        bids = [
            (-key, sum(o.remaining_qty for o in level))
            for key, level in list(self._bids.items())[:depth]
        ]
        asks = [
            (key, sum(o.remaining_qty for o in level))
            for key, level in list(self._asks.items())[:depth]
        ]
        return {
            "symbol": self.symbol,
            "bids": bids,
            "asks": asks,
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "spread": self.spread(),
        }

    def __repr__(self) -> str:
        return (
            f"OrderBook({self.symbol} "
            f"bid={self.best_bid()} ask={self.best_ask()} "
            f"spread={self.spread()})"
        )
