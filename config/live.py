"""实盘/模拟盘配置"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LiveConfig:
    """实盘交易配置"""
    # Binance 合约测试网
    rest_base_url: str = "https://testnet.binancefuture.com"
    ws_base_url: str = "wss://fstream.binancefuture.com"

    # 下单参数
    order_timeout: int = 10
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    time_in_force: Literal["GTC", "GTX", "IOC", "FOK"] = "GTX"

    # 运行控制
    max_messages: int | None = 1800  # None = 持续运行


# 默认实例
LIVE_CONFIG = LiveConfig()
