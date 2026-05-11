"""交易所接口抽象基类

所有交易所实现（回测、模拟盘、实盘）须继承此类，
提供统一的交易操作接口。
"""

import asyncio
from abc import ABC, abstractmethod

from core.types import Symbol, OrderId


class Exchange(ABC):
    """交易所抽象基类（原 BaseExchange）"""

    def __init__(self):
        self._pending: dict[OrderId, asyncio.Event] = {}
        self._filled: set[OrderId] = set()

    @abstractmethod
    async def connect(self) -> None:
        """建立连接并完成身份验证"""

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接，释放资源"""

    @abstractmethod
    async def submit_market_order(
        self,
        symbol: Symbol,
        side: str,
        size: float,
    ) -> OrderId | None:
        """提交市价单

        Args:
            symbol: 交易对，如 "BTCUSDT"
            side: "buy" 或 "sell"
            size: 下单数量

        Returns:
            order_id: 订单 ID，失败返回 None
        """

    @abstractmethod
    async def submit_limit_order(
        self,
        symbol: Symbol,
        side: str,
        price: float,
        size: float,
        reduce_only: bool = False,
        post_only: bool = False,
    ) -> OrderId | None:
        """提交限价单

        Args:
            symbol: 交易对
            side: 买卖方向
            price: 限价价格
            size: 下单数量
            reduce_only: 仅减仓
            post_only: 只做 Maker（GTX）

        Returns:
            order_id: 订单 ID，失败返回 None
        """

    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> None:
        """撤销订单"""

    @abstractmethod
    async def get_order_status(self, symbol: Symbol, order_id: OrderId) -> str | None:
        """查询订单状态"""

    def notify_fill(self, order_id: OrderId) -> None:
        """通知订单已成交

        由交易所实现调用，触发 wait_for_fill 返回。
        若 wait_for_fill 尚未注册，先缓存到 _filled，
        注册时立即返回。
        """
        event = self._pending.get(order_id)
        if event is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                event.set()
        else:
            self._filled.add(order_id)

    async def wait_for_fill(self, order_id: OrderId) -> None:
        """等待订单成交

        替代轮询，通过事件驱动方式等待成交通知。
        若订单已提前成交（notify_fill 早于 wait_for_fill），立即返回。
        """
        if order_id in self._filled:
            self._filled.discard(order_id)
            return

        event = asyncio.Event()
        self._pending[order_id] = event
        try:
            await event.wait()
        finally:
            self._pending.pop(order_id, None)
            self._filled.discard(order_id)
