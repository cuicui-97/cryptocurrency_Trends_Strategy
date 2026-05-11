"""核心类型定义

使用 dataclass 替代 TypedDict，提供更好的类型安全和 IDE 支持。
所有价格/数量使用 float，但业务逻辑中应注意精度问题。
"""

from dataclasses import dataclass
from typing import Literal, TypedDict


# 基础数据类型
Price = float
Size = float
Symbol = str
OrderId = str
TradeId = str
TimestampMs = int


@dataclass(frozen=True, slots=True)
class Trade:
    """成交数据

    在 DataFeed → StrategyRunner → SignalStrategy 之间传递
    """
    symbol: Symbol
    trade_id: TradeId
    price: Price
    size: Size
    side: Literal["buy", "sell"]
    timestamp_ms: TimestampMs
    is_buyer_maker: bool
    count: int | None = None


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """订单簿档位"""
    price: Price
    size: Size


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """订单簿快照

    DataFeed → Exchange 之间传递
    """
    symbol: Symbol
    timestamp_ms: TimestampMs
    bids: list[OrderBookLevel]   # 按价格降序
    asks: list[OrderBookLevel]   # 按价格升序


# 为了保持向后兼容，保留 TypedDict 版本用于 CSV 解析等场景
class TradeDataLegacy(TypedDict):
    """兼容旧代码的 Trade 字典格式"""
    instId: str
    tradeId: str
    px: str
    sz: str
    side: str
    ts: str
    count: int | None


class OrderBookSnapshotLegacy(TypedDict):
    """兼容旧代码的快照字典格式"""
    bids: list[list[float]]
    asks: list[list[float]]
