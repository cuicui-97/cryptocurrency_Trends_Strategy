"""
订单数据结构和状态机

状态流转：
  NEW → PARTIALLY_FILLED → FILLED
  NEW → CANCELED
  NEW → REJECTED（GTX 被拒、FOK 无法完全成交）
"""

from dataclasses import dataclass
from enum import Enum

# 浮点数精度容差，小于此值视为零
QTY_EPSILON = 1e-8


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(Enum):
    GTC = "GTC"   # Good Till Cancel：挂单直到成交或撤单
    GTX = "GTX"   # Post Only：若会立即成交则拒绝，只做 Maker
    IOC = "IOC"   # Immediate Or Cancel：立即成交剩余撤单
    FOK = "FOK"   # Fill Or Kill：必须完全成交否则全部撤单


class OrderStatus(Enum):
    NEW = "NEW"                            # 已提交，等待成交
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
    FILLED = "FILLED"                      # 完全成交
    CANCELED = "CANCELED"                  # 已撤销
    REJECTED = "REJECTED"                  # 被拒绝（GTX/FOK）


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float                        # 原始下单数量
    created_at: int                        # 时间戳（毫秒）
    price: float | None = None             # 限价单价格，市价单为 None
    time_in_force: TimeInForce = TimeInForce.GTC
    filled_qty: float = 0.0                # 已成交数量
    status: OrderStatus = OrderStatus.NEW

    @property
    def remaining_qty(self) -> float:
        return round(self.quantity - self.filled_qty, 8)

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def fill(self, qty: float) -> None:
        """更新成交数量和状态"""
        self.filled_qty = round(self.filled_qty + qty, 8)
        if self.remaining_qty <= QTY_EPSILON:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED

    def __repr__(self) -> str:
        return (
            f"Order({self.order_id} {self.side.value} {self.order_type.value} "
            f"qty={self.quantity} filled={self.filled_qty} "
            f"price={self.price} status={self.status.value})"
        )
