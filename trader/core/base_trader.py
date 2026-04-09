from abc import ABC, abstractmethod


class BaseTrader(ABC):
    """交易执行抽象基类，所有交易所实现须继承此类"""

    @abstractmethod
    async def connect_and_login(self) -> None:
        """建立连接并完成身份验证"""

    @abstractmethod
    async def place_limit_order(self, symbol: str, side: str,
                                price: float, size: float) -> None:
        """下限价单，超时后自动撤单"""

    async def close(self) -> None:
        """释放连接资源，子类按需覆盖"""
