"""回测数据回放器

从 CSV 文件读取历史数据，驱动回测引擎：
  - aggTrades CSV：逐笔成交，驱动信号生成 + 触发撮合
  - bookDepth CSV：订单簿快照，维护真实市场深度

DataFetcher 只负责数据驱动，不关心撮合细节，
撮合逻辑完全封装在 BacktestExchange 内部。

每条 aggTrade 的处理流程：
  1. 找最近订单簿快照，有变化时同步到交易所（exchange.sync_order_book）
  2. 通知交易所有新成交（exchange.on_agg_trade），触发订单簿撮合
  3. 推送成交数据给策略信号生成器

speed 参数控制回放速度：
  speed=0    全速回放（默认，几秒跑完几小时数据）
  speed=1.0  按真实时间回放（1倍速）
  speed=2.0  2倍速（真实时间的一半）
  speed=0.5  0.5倍速（慢放，方便调试）

bookDepth CSV 格式（collect_data.py 采集）：
  timestamp, bids, asks
"""

import asyncio
import bisect
import csv
import json
from datetime import datetime
from pathlib import Path

from config import BACKTEST_CONFIG
from config import STRATEGY_CONFIG
from core.data_feed import DataFeed
from core.logger import make_logger
from core.types import Trade, OrderBookSnapshot, TradeDataLegacy as TradeData
from backtest.exchange import BacktestExchange
from config.base import TradingConfig


class BacktestDataFeed(DataFeed):

    def __init__(self, trades_csv: str | Path,
                 book_csv: str | Path,
                 exchange: BacktestExchange,
                 symbol: str = TradingConfig().symbol,
                 speed: float = 0):
        """
        speed: 回放速度倍率
          0    — 全速（默认）
          1.0  — 按真实时间
          2.0  — 2倍速
          0.5  — 半速（慢放）
          任意正数均可
        """
        super().__init__(symbol, max_messages=None)
        self._trades_csv = Path(trades_csv)
        self._book_csv   = Path(book_csv)
        self._exchange   = exchange
        self._speed      = speed
        self.logger = make_logger(__name__, STRATEGY_CONFIG.log_file)
        self._book_index:      dict[str, OrderBookSnapshot] = {}
        self._book_timestamps: list[str]                   = []

    # ─────────────────────────────────────────────────────
    # BaseDataFetcher 接口
    # ─────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._load_book_index()
        self.logger.info(
            f"[回测] 订单簿快照加载完成，共 {len(self._book_timestamps)} 个时间点"
        )

        count      = 0
        last_snapshot = None
        prev_ts_ms    = None   # 上一条 aggTrade 的时间戳，用于计算间隔

        speed_desc = f"{self._speed}x" if self._speed > 0 else "全速"
        self.logger.info(f"[回测] 开始回放，速度={speed_desc}")

        with open(self._trades_csv, newline="") as f:
            for row in csv.DictReader(f):
                row: dict[str, str]  # csv.DictReader 返回值类型收窄
                ts_ms          = int(row["transact_time"])
                price          = float(row["price"])
                qty            = float(row["quantity"])
                is_buyer_maker = row["is_buyer_maker"].lower() == "true"

                # 快照有变化时同步市场深度
                snapshot = self._find_snapshot(ts_ms)
                if snapshot is not None and snapshot is not last_snapshot:
                    self._exchange.sync_order_book(snapshot)
                    self.order_book_deque.append(snapshot)
                    last_snapshot = snapshot

                # 触发撮合
                self._exchange.on_agg_trade(price, qty, is_buyer_maker)

                # 推给策略信号生成器
                trade: TradeData = {
                    'instId':  self.instId,
                    'tradeId': row["agg_trade_id"],
                    'px':      row["price"],
                    'sz':      row["quantity"],
                    'side':    'sell' if is_buyer_maker else 'buy',
                    'ts':      row["transact_time"],
                    'count':   None,
                }
                await self.trade_queue.put(trade)
                count += 1

                if count % 50000 == 0:
                    self.logger.info(f"[回测] 已回放 {count:,} 笔成交")

                # 速度控制
                if self._speed > 0 and prev_ts_ms is not None:
                    interval = (ts_ms - prev_ts_ms) / 1000 / self._speed
                    if interval > 0:
                        await asyncio.sleep(interval)
                    else:
                        await asyncio.sleep(0)
                else:
                    await asyncio.sleep(0)

                prev_ts_ms = ts_ms

        self.logger.info(f"[回测] 回放完成，共 {count:,} 笔成交")
        self.stop_flag.set()

    async def on_stop(self) -> None:
        self.stop_flag.set()

    # ─────────────────────────────────────────────────────
    # 订单簿快照索引
    # ─────────────────────────────────────────────────────

    def _load_book_index(self) -> None:
        """
        加载 bookDepth CSV。格式：每行一个时间点
          timestamp, bids, asks
        bids/asks 是 JSON 数组：[[price, qty], ...]，已按价格排序。
        """
        with open(self._book_csv, newline="") as f:
            for row in csv.DictReader(f):
                row: dict[str, str]
                ts: str = row["timestamp"]
                snapshot: OrderBookSnapshot = {
                    "bids": json.loads(row["bids"]),
                    "asks": json.loads(row["asks"]),
                }
                self._book_index[ts] = snapshot

        self._book_timestamps = sorted(self._book_index.keys())

    def _find_snapshot(self, ts_ms: int) -> OrderBookSnapshot | None:
        """
        找不超过当前时间的最近订单簿快照。
        自动适配秒级（%Y-%m-%d %H:%M:%S）和毫秒级（%Y-%m-%d %H:%M:%S.%f）时间戳。
        """
        if not self._book_timestamps:
            return None
        # 根据快照时间戳格式决定精度
        if '.' in self._book_timestamps[0]:
            ts_str = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        else:
            ts_str = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        idx = bisect.bisect_right(self._book_timestamps, ts_str)
        if idx == 0:
            return None
        return self._book_index[self._book_timestamps[idx - 1]]
