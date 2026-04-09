from abc import ABC, abstractmethod
from collections import deque
import asyncio


class BaseDataFetcher(ABC):
    """行情数据采集抽象基类，所有交易所实现须继承此类"""

    def __init__(self, symbol: str, max_messages: int | None):
        self.instId = symbol
        self.max_messages = max_messages
        self.message_count = 0
        self.stop_flag = asyncio.Event()
        self.data_deque: deque = deque()
        self.order_book_deque: deque = deque()
        self.trade_queue: asyncio.Queue = asyncio.Queue()

    @abstractmethod
    async def connect(self) -> None:
        """建立 WebSocket 连接并持续接收消息"""

    @abstractmethod
    async def on_stop(self) -> None:
        """断开连接，释放资源"""

    async def run(self) -> None:
        try:
            while not self.stop_flag.is_set():
                await self.connect()
        except KeyboardInterrupt:
            await self.on_stop()

    def get_latest_bid_price(self, depth: int = 0) -> float | None:
        """获取最新买盘第 depth 档价格（0=买一，2=买三，4=买五）"""
        if not self.order_book_deque:
            return None
        bids = self.order_book_deque[-1].get("bids", [])
        if len(bids) > depth:
            return float(bids[depth][0])
        return None

    def get_latest_ask_price(self, depth: int = 0) -> float | None:
        """获取最新卖盘第 depth 档价格（0=卖一，2=卖三，4=卖五）"""
        if not self.order_book_deque:
            return None
        asks = self.order_book_deque[-1].get("asks", [])
        if len(asks) > depth:
            return float(asks[depth][0])
        return None

    def get_latest_bid0_price(self) -> float | None:
        return self.get_latest_bid_price(0)

    def get_latest_bid2_price(self) -> float | None:
        return self.get_latest_bid_price(2)

    def get_latest_bid4_price(self) -> float | None:
        return self.get_latest_bid_price(4)

    def get_latest_ask0_price(self) -> float | None:
        return self.get_latest_ask_price(0)

    def get_latest_ask2_price(self) -> float | None:
        return self.get_latest_ask_price(2)

    def get_latest_ask4_price(self) -> float | None:
        return self.get_latest_ask_price(4)
