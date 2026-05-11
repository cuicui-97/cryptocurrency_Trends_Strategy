"""基础配置类

使用 dataclass 替代全局变量，提供类型安全和不可变性。
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TradingConfig:
    """交易基础配置"""
    symbol: str = "BTCUSDT"
    order_size: float = 0.003
    leverage: int = 1
    margin_type: Literal["ISOLATED", "CROSSED"] = "ISOLATED"


@dataclass(frozen=True)
class LoggingConfig:
    """日志配置"""
    execution_log_file: str = "logs/execution_info.log"
    trade_log_file: str = "logs/trade_data.log"
    order_book_log_file: str = "logs/order_book.log"


@dataclass(frozen=True)
class SignalConfig:
    """信号生成配置"""
    window_size: int = 30
    threshold_long: float = 0.05
    threshold_short: float = -0.05


@dataclass(frozen=True)
class RiskConfig:
    """风险控制配置"""
    take_profit_spread: float = 0.0005  # 止盈目标价差
    stop_loss_spread: float = 0.0008    # 止损比例
