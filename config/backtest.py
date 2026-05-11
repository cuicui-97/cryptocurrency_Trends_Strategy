"""回测配置"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BacktestConfig:
    """回测参数配置"""
    # 数据文件路径
    trades_csv: Path = Path("backtest/data/aggTrades/BTCUSDT-aggTrades-2026-04-12.csv")
    book_csv: Path = Path("backtest/data/bookDepth/BTCUSDT-bookDepth-2026-04-12.csv")

    # 回放速度：0 = 全速，1.0 = 真实时间
    playback_speed: float = 0.0


# 默认实例
BACKTEST_CONFIG = BacktestConfig()
