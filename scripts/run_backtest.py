"""
回测入口

用历史数据驱动策略，通过撮合引擎模拟成交。

用法：
  uv run python run_backtest.py                  # 全速回放
  uv run python run_backtest.py --speed 1.0      # 按真实时间回放
  uv run python run_backtest.py --speed 10.0     # 10倍速
  uv run python run_backtest.py --speed 0.5      # 0.5倍速（慢放调试）
  uv run python run_backtest.py --trades path/to/aggTrades.csv --book path/to/bookDepth.csv
"""

import argparse
import asyncio
from pathlib import Path

from config import BACKTEST_CONFIG
from backtest.data_feed import BacktestDataFeed
from backtest.exchange import BacktestExchange
from strategy.runner import StrategyRunner


def main():
    parser = argparse.ArgumentParser(description="撮合引擎回测")
    parser.add_argument("--trades", default=BACKTEST_CONFIG.DEFAULT_TRADES_CSV, help="aggTrades CSV 路径")
    parser.add_argument("--book",   default=BACKTEST_CONFIG.DEFAULT_BOOK_CSV,   help="bookDepth CSV 路径")
    parser.add_argument("--speed",  type=float, default=BACKTEST_CONFIG.DEFAULT_SPEED,
                        help="回放速度倍率：0=全速，1.0=真实时间，2.0=2倍速（默认0）")
    args = parser.parse_args()

    trades_path = Path(args.trades)
    book_path   = Path(args.book)

    if not trades_path.exists():
        raise FileNotFoundError(f"找不到成交数据文件: {trades_path}")
    if not book_path.exists():
        raise FileNotFoundError(f"找不到订单簿数据文件: {book_path}")

    Path("logs").mkdir(exist_ok=True)

    exchange = BacktestExchange()
    fetcher  = BacktestDataFeed(
        trades_csv=trades_path,
        book_csv=book_path,
        exchange=exchange,
        speed=args.speed,
    )
    runner = StrategyRunner(fetcher=fetcher, exchange=exchange)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
