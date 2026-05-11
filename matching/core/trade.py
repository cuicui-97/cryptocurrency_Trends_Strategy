"""
成交记录

每次撮合产生一条 Trade，记录双方订单 ID、成交价格、数量和时间。
"""

from dataclasses import dataclass


@dataclass
class Trade:
    trade_id: str
    symbol: str
    price: float
    quantity: float
    buyer_order_id: str
    seller_order_id: str
    timestamp: int           # 毫秒时间戳
    is_buyer_maker: bool     # True = 买方是挂单方（卖方主动成交）

    @property
    def notional(self) -> float:
        """成交金额（USDT）"""
        return round(self.price * self.quantity, 6)

    def __repr__(self) -> str:
        maker = "buyer" if self.is_buyer_maker else "seller"
        return (
            f"Trade({self.trade_id} {self.symbol} "
            f"price={self.price} qty={self.quantity} "
            f"maker={maker})"
        )
