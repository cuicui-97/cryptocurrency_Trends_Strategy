"""行情数据馈送抽象基类

所有数据源实现（回测、实时 WebSocket、REST 轮询）须继承此类。
"""

from abc import ABC, abstractmethod
from collections import deque
import asyncio

from core.types import Trade, OrderBookSnapshot, Symbol


class DataFeed(ABC):
    """数据馈送抽象基类（原 BaseDataFetcher）"""

    def __init__(
        self,
        symbol: Symbol,
        max_messages: int | None = None,
    ):
        self.symbol = symbol
        self.max_messages = max_messages
        self.message_count = 0
        self.stop_flag = asyncio.Event()

        # 数据队列和缓存
        self.trade_queue: asyncio.Queue[Trade] = asyncio.Queue()
        self.trade_history: deque[Trade] = deque()
        self.order_book_history: deque[OrderBookSnapshot] = deque()

    @abstractmethod
    async def connect(self) -> None:
        """建立连接并开始接收数据"""

    @abstractmethod
    async def on_stop(self) -> None:
        """停止接收，释放资源"""

    async def run(self) -> None:
        """主运行循环"""
        try:
            while not self.stop_flag.is_set():
                await self.connect()
        except KeyboardInterrupt:
            await self.on_stop()

    def get_latest_bid(self, depth: int = 0) -> float | None:
        """获取最新买盘第 depth 档价格（0=买一）"""
        if not self.order_book_history:
            return None
        bids = self.order_book_history[-1].bids
        if len(bids) > depth:
            return bids[depth].price
        return None

    def get_latest_ask(self, depth: int = 0) -> float | None:
        """获取最新卖盘第 depth 档价格（0=卖一）"""
        if not self.order_book_history:
            return None
        asks = self.order_book_history[-1].asks
        if len(asks) > depth:
            return asks[depth].price
        return None

    def push_trade(self, trade: Trade) -> None:
        """推送成交数据到队列和历史记录"""
        self.trade_queue.put_nowait(trade)
        self.trade_history.append(trade)
        self.message_count += 1

    def push_order_book(self, snapshot: OrderBookSnapshot) -> None:
        """推送订单簿快照到历史记录"""
        self.order_book_history.append(snapshot)
