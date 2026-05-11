"""策略配置

组合基础配置，提供策略运行所需的完整配置集合。
"""

from config.base import TradingConfig, LoggingConfig, SignalConfig, RiskConfig


class StrategyConfig:
    """策略完整配置"""

    def __init__(
        self,
        trading: TradingConfig | None = None,
        logging: LoggingConfig | None = None,
        signal: SignalConfig | None = None,
        risk: RiskConfig | None = None,
    ):
        self.trading = trading or TradingConfig()
        self.logging = logging or LoggingConfig()
        self.signal = signal or SignalConfig()
        self.risk = risk or RiskConfig()

    @property
    def window_size(self) -> int:
        return self.signal.window_size

    @property
    def threshold_long(self) -> float:
        return self.signal.threshold_long

    @property
    def threshold_short(self) -> float:
        return self.signal.threshold_short

    @property
    def order_size(self) -> float:
        return self.trading.order_size

    @property
    def take_profit_spread(self) -> float:
        return self.risk.take_profit_spread

    @property
    def stop_loss_spread(self) -> float:
        return self.risk.stop_loss_spread

    @property
    def log_file(self) -> str:
        return self.logging.trader_log_file


# 默认实例
STRATEGY_CONFIG = StrategyConfig()
