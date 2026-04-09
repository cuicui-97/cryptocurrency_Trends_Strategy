"""
Binance 历史数据下载脚本

数据来源：https://data.binance.vision
下载内容：
  - aggTrades：逐笔成交（价格、数量、方向）
  - bookDepth：订单簿快照（400档深度，每100ms一次）

用法：
  python backtest/download_data.py --date 2026-04-08
  python backtest/download_data.py --date 2026-04-08 --days 3
"""

import argparse
import io
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "https://data.binance.vision/data/futures/um/daily"
SYMBOL = "BTCUSDT"
DATA_DIR = Path("backtest/data")


def download_file(url: str, dest: Path) -> bool:
    """下载并解压 zip 文件到目标目录"""
    if dest.exists():
        print(f"  已存在，跳过: {dest.name}")
        return True

    print(f"  下载: {url}")
    resp = requests.get(url, timeout=60)
    if resp.status_code == 404:
        print(f"  不存在: {url}")
        return False
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(dest.parent)
    print(f"  解压完成: {dest.name}")
    return True


def download_day(date_str: str):
    """下载指定日期的成交和订单簿数据"""
    print(f"\n=== {date_str} ===")

    # aggTrades：逐笔成交
    agg_dir = DATA_DIR / "aggTrades"
    agg_dir.mkdir(parents=True, exist_ok=True)
    agg_csv = agg_dir / f"{SYMBOL}-aggTrades-{date_str}.csv"
    agg_url = f"{BASE_URL}/aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-{date_str}.zip"
    download_file(agg_url, agg_csv)

    # bookDepth：订单簿快照（400档深度）
    book_dir = DATA_DIR / "bookDepth"
    book_dir.mkdir(parents=True, exist_ok=True)
    book_csv = book_dir / f"{SYMBOL}-bookDepth-{date_str}.csv"
    book_url = f"{BASE_URL}/bookDepth/{SYMBOL}/{SYMBOL}-bookDepth-{date_str}.zip"
    download_file(book_url, book_csv)


def main():
    parser = argparse.ArgumentParser(description="下载 Binance 历史数据")
    parser.add_argument("--date", default=None,
                        help="日期，格式 YYYY-MM-DD，默认昨天")
    parser.add_argument("--days", type=int, default=1,
                        help="下载天数，从 date 往前推，默认 1 天")
    args = parser.parse_args()

    if args.date:
        end_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        end_date = datetime.now() - timedelta(days=1)

    dates = [
        (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(args.days - 1, -1, -1)
    ]

    print(f"下载 {SYMBOL} 数据，共 {len(dates)} 天: {dates[0]} ~ {dates[-1]}")

    for date_str in dates:
        download_day(date_str)

    print("\n完成！数据保存在 backtest/data/")
    print("  aggTrades/  — 逐笔成交")
    print("  bookDepth/  — 订单簿快照（400档）")


if __name__ == "__main__":
    main()
