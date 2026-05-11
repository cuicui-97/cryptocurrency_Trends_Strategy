"""
回测数据采集脚本

同时采集两个 WebSocket 流并保存到 CSV：
  - aggTrades：逐笔成交（用于信号生成）
  - depth20@100ms：20档订单簿快照，绝对价格（用于开仓报价）

输出文件：
  backtest/data/aggTrades/BTCUSDT-aggTrades-<date>.csv
  backtest/data/bookDepth/BTCUSDT-bookDepth-<date>.csv

bookDepth 格式：每行一个时间点，bids/asks 用 JSON 数组存储
  timestamp, bids, asks
  2026-04-11 00:41:05, "[[72663.9,0.085],[...]]", "[[72672.0,0.313],[...]]"

用法：
  uv run python collect_data.py --duration 7200   # 采集2小时
"""

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import websockets

SYMBOL = "BTCUSDT"
WS_URL = (
    f"wss://fstream.binancefuture.com/stream"
    f"?streams={SYMBOL.lower()}@aggTrade/{SYMBOL.lower()}@depth20@100ms"
)

TRADE_FIELDS = ["agg_trade_id", "price", "quantity",
                "first_trade_id", "last_trade_id",
                "transact_time", "is_buyer_maker"]
BOOK_FIELDS  = ["timestamp", "bids", "asks"]


async def collect(duration: int, output_dir: Path):
    date_str = datetime.now().strftime("%Y-%m-%d")
    trades_path = output_dir / "aggTrades" / f"{SYMBOL}-aggTrades-{date_str}.csv"
    book_path   = output_dir / "bookDepth"  / f"{SYMBOL}-bookDepth-{date_str}.csv"

    trades_path.parent.mkdir(parents=True, exist_ok=True)
    book_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"开始采集，持续 {duration // 60} 分钟...")
    print(f"  aggTrades → {trades_path}")
    print(f"  bookDepth → {book_path}")

    trade_count = 0
    book_count  = 0
    start = time.time()
    end_time = start + duration

    with open(trades_path, "w", newline="", buffering=1) as tf, \
         open(book_path,   "w", newline="", buffering=1) as bf:

        trade_writer = csv.DictWriter(tf, fieldnames=TRADE_FIELDS)
        book_writer  = csv.DictWriter(bf, fieldnames=BOOK_FIELDS)
        trade_writer.writeheader()
        book_writer.writeheader()

        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    print("WebSocket 已连接")
                    while time.time() < end_time:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            continue

                        wrapper = json.loads(raw)
                        stream  = wrapper.get("stream", "")
                        data    = wrapper.get("data", {})

                        if "aggTrade" in stream:
                            trade_writer.writerow({
                                "agg_trade_id":   data["a"],
                                "price":          data["p"],
                                "quantity":       data["q"],
                                "first_trade_id": data["f"],
                                "last_trade_id":  data["l"],
                                "transact_time":  data["T"],
                                "is_buyer_maker": data["m"],
                            })
                            trade_count += 1
                            if trade_count % 10000 == 0:
                                remaining = int(end_time - time.time())
                                print(f"  [{remaining}s 剩余] 成交 {trade_count:,} 笔 | 订单簿 {book_count:,} 条")

                        elif "depth" in stream:
                            # 优先用推送数据里的事件时间（毫秒），保留完整精度
                            ts_ms = data.get("T") or data.get("E")
                            if ts_ms:
                                ts = datetime.fromtimestamp(int(ts_ms)/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            else:
                                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            bids = data.get("b") or data.get("bids", [])
                            asks = data.get("a") or data.get("asks", [])
                            book_writer.writerow({
                                "timestamp": ts,
                                "bids":      json.dumps([[float(p), float(q)] for p, q in bids]),
                                "asks":      json.dumps([[float(p), float(q)] for p, q in asks]),
                            })
                            book_count += 1

                    # 时间到，正常退出
                    break

            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                print(f"连接断开: {e}，2秒后重连...")
                await asyncio.sleep(2)
                if time.time() >= end_time:
                    break

    elapsed = time.time() - start
    print(f"\n采集完成！耗时 {elapsed:.0f}s")
    print(f"  成交数据：{trade_count:,} 笔 → {trades_path}")
    print(f"  订单簿快照：{book_count:,} 条 → {book_path}")


def main():
    parser = argparse.ArgumentParser(description="采集 Binance 回测数据")
    parser.add_argument("--duration", type=int, default=7200,
                        help="采集时长（秒），默认 7200（2小时）")
    parser.add_argument("--output", default="backtest/data",
                        help="输出根目录")
    args = parser.parse_args()
    asyncio.run(collect(args.duration, Path(args.output)))


if __name__ == "__main__":
    main()
