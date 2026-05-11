"""
Binance 行情数据采集（无需 API Key）

使用两个 WebSocket 流：
  - aggTrade：逐笔成交
  - depth20：20 档订单簿快照（100ms 推送）
"""

import asyncio
import json
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

import config
import live.config as live_config
from core.base_data_fetcher import BaseDataFetcher
from core.logger import make_logger
from core.types import TradeData, OrderBookSnapshot

_SYMBOL = config.SYMBOL.lower()
_WS_URL = (
    f"{live_config.WS_BASE_URL}/stream"
    f"?streams={_SYMBOL}@aggTrade/{_SYMBOL}@depth20@100ms"
)


class BinanceDataFetcher(BaseDataFetcher):

    def __init__(self, symbol: str = config.SYMBOL,
                 max_messages: int | None = live_config.MAX_MESSAGES):
        super().__init__(symbol, max_messages)
        self._ws: ClientConnection | None = None
        self.trade_logger = make_logger("data.trade", live_config.TRADE_LOG_FILE)
        self.book_logger  = make_logger("data.orderbook", live_config.ORDER_BOOK_LOG_FILE)

    async def connect(self) -> None:
        try:
            self.trade_logger.info(f"正在连接 WebSocket: {_WS_URL}")
            self._ws = await websockets.connect(_WS_URL)
            self.trade_logger.info("WebSocket 连接成功，开始接收行情数据")

            while not self.stop_flag.is_set():
                message = await self._ws.recv()
                await self._process_message(str(message))

                if self.max_messages and self.message_count >= self.max_messages:
                    self.trade_logger.info(f"已达到最大消息数 {self.max_messages}，停止采集")
                    self.stop_flag.set()

        except websockets.exceptions.ConnectionClosed as e:
            self.trade_logger.error(f"WebSocket 连接断开: {e}，2秒后重连...")
            await asyncio.sleep(2)
        except Exception as e:
            self.trade_logger.error(f"WebSocket 连接异常: {e}，2秒后重连...")
            await asyncio.sleep(2)

    async def _process_message(self, message: str) -> None:
        try:
            wrapper: dict[str, Any] = json.loads(message)
            stream = wrapper.get("stream", "")
            data: dict[str, Any] = wrapper.get("data", {})

            if "aggTrade" in stream:
                await self._handle_trade(data)
            elif "depth" in stream:
                self._handle_order_book(data)

        except json.JSONDecodeError as e:
            self.trade_logger.error(f"JSON decode error: {e}")
        except Exception as e:
            self.trade_logger.error(f"Message processing error: {e}")

    async def _handle_trade(self, data: dict[str, Any]) -> None:
        trade: TradeData = {
            'instId':  self.instId,
            'tradeId': str(data['a']),
            'px':      str(data['p']),
            'sz':      str(data['q']),
            'side':    'sell' if data.get('m') else 'buy',
            'ts':      str(data['T']),
            'count':   None,
        }
        self.data_deque.append(trade)
        self.message_count += 1
        self.trade_logger.info(
            f"#{self.message_count} tradeId={trade['tradeId']} "
            f"price={trade['px']} size={trade['sz']} side={trade['side']}"
        )
        await self.trade_queue.put(trade)

    def _handle_order_book(self, data: dict[str, Any]) -> None:
        snapshot: OrderBookSnapshot = {
            "bids": [[float(p), float(q)] for p, q in (data.get("b") or data.get("bids", []))],
            "asks": [[float(p), float(q)] for p, q in (data.get("a") or data.get("asks", []))],
        }
        self.order_book_deque.append(snapshot)

        if len(self.order_book_deque) % 50 == 0 and snapshot["bids"] and snapshot["asks"]:
            self.book_logger.info(
                f"买一={snapshot['bids'][0][0]} 卖一={snapshot['asks'][0][0]} "
                f"买一量={snapshot['bids'][0][1]} 卖一量={snapshot['asks'][0][1]}"
            )

    async def on_stop(self) -> None:
        self.stop_flag.set()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self.trade_logger.info("WebSocket 已关闭")
