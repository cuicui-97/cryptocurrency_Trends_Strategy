"""
策略引擎

只负责协调各模块：
  1. 启动行情采集
  2. 驱动信号生成
  3. 触发开仓执行
"""

import asyncio
import time

from config import STRATEGY_CONFIG
from core.data_feed import DataFeed
from core.types import Trade
from core.exchange import Exchange
from core.logger import make_logger
from strategy.signal_generator import SignalGenerator
from strategy.order_executor import OrderExecutor
from strategy.pnl_tracker import PnlTracker


class StrategyRunner:

    def __init__(self, fetcher: DataFeed, exchange: Exchange):
        self.fetcher = fetcher
        self.exchange = exchange
        self.signal_generator = SignalGenerator()
        self.pnl_tracker = PnlTracker()
        self.order_executor = OrderExecutor(exchange=exchange, pnl_tracker=self.pnl_tracker)
        self.logger = make_logger(__name__, STRATEGY_CONFIG.TRADER_LOG_FILE)

    async def run(self) -> None:
        self.logger.info("=" * 50)
        self.logger.info(
            f"策略启动: symbol={self.fetcher.symbol} "
            f"window={self.signal_generator.window_size} "
            f"long={STRATEGY_CONFIG.threshold_long} short={STRATEGY_CONFIG.threshold_short}"
        )
        self.logger.info("=" * 50)

        await self.exchange.connect()
        fetcher_task = asyncio.create_task(self.fetcher.run())

        trade_count = 0
        window_start = time.time()

        try:
            while not self.fetcher.stop_flag.is_set():
                try:
                    trade = await asyncio.wait_for(
                        self.fetcher.trade_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                trade_count += 1

                queue_size = self.fetcher.trade_queue.qsize()
                if queue_size > 10:
                    self.logger.warning(f"[引擎] 队列积压 {queue_size} 条")

                self.logger.info(
                    f"[引擎] 第 {trade_count} 笔: "
                    f"price={trade['px']} size={trade['sz']} side={trade['side']} "
                    f"队列剩余={queue_size}"
                )

                if (trade_count - 1) % STRATEGY_CONFIG.window_size == 0:
                    window_start = time.time()

                self.signal_generator.add_trade(trade)

                if self.signal_generator.is_window_complete(trade_count):
                    self._on_window_complete(trade_count, window_start)

        except Exception as e:
            self.logger.error(f"[引擎] 运行异常: {e}")
        finally:
            self.logger.info("[引擎] 主循环结束")
            self.logger.info(f"[最终统计] {self.pnl_tracker.summary()}")
            await self.exchange.disconnect()
            await fetcher_task

    def _on_window_complete(self, trade_count: int, window_start: float) -> None:
        intensity = self.signal_generator.last_intensity
        elapsed = time.time() - window_start
        self.logger.info(
            f"[窗口] 第 {trade_count // STRATEGY_CONFIG.window_size} 窗口 "
            f"耗时={elapsed:.3f}s 强度={intensity:.6f}"
        )

        signal = self.signal_generator.get_signal()
        if signal:
            price = (self.fetcher.get_latest_bid(0) if signal == "buy"
                     else self.fetcher.get_latest_ask(0))
            if price is None:
                self.logger.warning("[引擎] 无法获取价格，跳过下单")
                return
            self.logger.info(f"[信号] {signal.upper()} price={price}")
            self.order_executor.execute(
                self.fetcher.symbol, signal, price, STRATEGY_CONFIG.order_size
            )
        else:
            self.logger.info(f"[信号] 强度 {intensity:.4f} 未超阈值，无信号")
