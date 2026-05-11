"""
模拟盘入口

连接 Binance 合约测试网，实时运行策略。

用法：
  export BINANCE_API_KEY=your_key
  export BINANCE_SECRET_KEY=your_secret
  uv run python run_live.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from live.data_fetcher import BinanceDataFetcher
from live.exchange import BinanceExchange
from strategy.runner import StrategyRunner

load_dotenv()

api_key = os.environ.get("BINANCE_API_KEY", "")
secret_key = os.environ.get("BINANCE_SECRET_KEY", "")

if not all([api_key, secret_key]):
    raise ValueError(
        "请先设置环境变量：BINANCE_API_KEY、BINANCE_SECRET_KEY\n"
        "示例：export BINANCE_API_KEY=your_key"
    )

Path("logs").mkdir(exist_ok=True)

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    exchange = BinanceExchange(api_key=api_key, secret_key=secret_key)
    engine = StrategyRunner(fetcher=fetcher, exchange=exchange)
    asyncio.run(engine.run())
