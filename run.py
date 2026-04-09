import asyncio
import os

from dotenv import load_dotenv

from exchange.binance.data_fetcher import BinanceDataFetcher
from exchange.binance.trader import BinanceTrader
from strategy.engine import TradingEngine

load_dotenv()

api_key = os.environ.get("BINANCE_API_KEY", "")
secret_key = os.environ.get("BINANCE_SECRET_KEY", "")

if not all([api_key, secret_key]):
    raise ValueError(
        "请先设置环境变量：BINANCE_API_KEY、BINANCE_SECRET_KEY\n"
        "示例：export BINANCE_API_KEY=your_key"
    )

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    trader = BinanceTrader(api_key=api_key, secret_key=secret_key)
    engine = TradingEngine(fetcher=fetcher, trader=trader)
    asyncio.run(engine.run())
