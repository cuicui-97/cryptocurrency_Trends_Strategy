"""
Binance U本位永续合约交易执行（REST API，HMAC-SHA256 签名）

分两层：
  _api_xxx()  — 底层，纯 HTTP 请求，只负责发请求返回原始数据
  业务方法()  — 上层，组合 API 调用，处理业务逻辑

成交通知：
  轮询到订单成交后调用 self.notify_fill(order_id)，
  唤醒 OrderExecutor 中 wait_for_fill() 等待的协程。
"""

import asyncio
import hashlib
import hmac
import time

import aiohttp

import config
import live.config as live_config
import strategy.config as strategy_config
from core.base_trader import BaseExchange
from core.logger import make_logger


class BinanceExchange(BaseExchange):

    def __init__(self, api_key: str, secret_key: str,
                 order_timeout: int = live_config.ORDER_TIMEOUT,
                 log_file: str = strategy_config.TRADER_LOG_FILE):
        super().__init__()
        self.api_key = api_key
        self.secret_key = secret_key
        self.order_timeout = order_timeout
        self.base_url = live_config.REST_BASE_URL
        self._session: aiohttp.ClientSession | None = None
        self.logger = make_logger(__name__, log_file)

    # ─────────────────────────────────────────────────────
    # 签名与请求头
    # ─────────────────────────────────────────────────────

    def _sign(self, params: str) -> str:
        return hmac.new(
            self.secret_key.encode(), params.encode(), hashlib.sha256
        ).hexdigest()

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    # ─────────────────────────────────────────────────────
    # 底层 API
    # ─────────────────────────────────────────────────────

    async def _api_request(self, method: str, path: str, params: str) -> dict[str, object]:
        assert self._session is not None, "_session 未初始化，请先调用 connect_and_login()"
        url = f"{self.base_url}{path}?{params}&signature={self._sign(params)}"
        async with self._session.request(method, url) as resp:
            return await resp.json()

    async def _api_get(self, path: str, params: str) -> dict[str, object]:
        return await self._api_request("GET", path, params)

    async def _api_post(self, path: str, params: str) -> dict[str, object]:
        return await self._api_request("POST", path, params)

    async def _api_delete(self, path: str, params: str) -> dict[str, object]:
        return await self._api_request("DELETE", path, params)

    async def _api_get_account(self) -> dict:
        params = f"timestamp={self._timestamp()}"
        return await self._api_get("/fapi/v2/account", params)

    async def _api_set_leverage(self, symbol: str, leverage: int) -> dict:
        params = f"symbol={symbol}&leverage={leverage}&timestamp={self._timestamp()}"
        return await self._api_post("/fapi/v1/leverage", params)

    async def _api_set_margin_type(self, symbol: str, margin_type: str) -> dict:
        params = f"symbol={symbol}&marginType={margin_type}&timestamp={self._timestamp()}"
        return await self._api_post("/fapi/v1/marginType", params)

    async def _api_submit_order(self, symbol: str, side: str, order_type: str,
                                quantity: float, price: float | None = None,
                                time_in_force: str | None = None,
                                reduce_only: bool = False) -> dict:
        params = (
            f"symbol={symbol}&side={side.upper()}"
            f"&type={order_type}&quantity={quantity}"
            f"&timestamp={self._timestamp()}"
        )
        if price is not None:
            params += f"&price={price}"
        if time_in_force is not None:
            params += f"&timeInForce={time_in_force}"
        if reduce_only:
            params += "&reduceOnly=true"
        return await self._api_post("/fapi/v1/order", params)

    async def _api_get_order(self, symbol: str, order_id: str) -> dict:
        params = f"symbol={symbol}&orderId={order_id}&timestamp={self._timestamp()}"
        return await self._api_get("/fapi/v1/order", params)

    async def _api_cancel_order(self, symbol: str, order_id: str) -> dict:
        params = f"symbol={symbol}&orderId={order_id}&timestamp={self._timestamp()}"
        return await self._api_delete("/fapi/v1/order", params)

    # ─────────────────────────────────────────────────────
    # 业务方法
    # ─────────────────────────────────────────────────────

    async def connect_and_login(self) -> None:
        self._session = aiohttp.ClientSession(headers=self._headers())
        try:
            self.logger.info(f"正在验证 API Key，服务器: {self.base_url}")
            data = await self._api_get_account()
            if "totalWalletBalance" in data:
                self.logger.info(f"API Key 验证成功，账户余额: {data['totalWalletBalance']} USDT")
            else:
                self.logger.error(f"API Key 验证失败: {data}")
                return

            data = await self._api_set_leverage(config.SYMBOL, live_config.LEVERAGE)
            self.logger.info(f"杠杆设置: {data.get('leverage')}x")

            data = await self._api_set_margin_type(config.SYMBOL, live_config.MARGIN_TYPE)
            if data.get("code") == 200 or "msg" in data:
                self.logger.info(f"保证金模式: {live_config.MARGIN_TYPE}")

        except Exception as e:
            self.logger.error(f"connect_and_login 失败: {e}")

    async def submit_market_order(self, symbol: str, side: str,
                                  size: float) -> str | None:
        try:
            self.logger.info(f"[市价单] {side.upper()} size={size}")
            data = await self._api_submit_order(
                symbol=symbol, side=side, order_type="MARKET", quantity=size
            )
            if "orderId" in data:
                oid = str(data["orderId"])
                self.logger.info(f"[市价单] 成功 orderId={oid}")
                # 市价单通常立即成交，启动轮询确认
                asyncio.create_task(self._poll_and_notify(symbol, oid))
                return oid
            self.logger.error(f"[市价单] 失败: {data.get('code')} {data.get('msg')}")
            return None
        except Exception as e:
            self.logger.error(f"[市价单] 异常: {e}")
            return None

    async def submit_limit_order(self, symbol: str, side: str,
                                 price: float, size: float,
                                 reduce_only: bool = False,
                                 post_only: bool = True) -> str | None:
        try:
            tif = live_config.TIME_IN_FORCE if post_only else "GTC"
            tag = "平仓限价单" if reduce_only else "开仓限价单"
            self.logger.info(f"[{tag}] {side.upper()} price={price} size={size} tif={tif}")
            data = await self._api_submit_order(
                symbol=symbol, side=side, order_type=live_config.ORDER_TYPE,
                quantity=size, price=price, time_in_force=tif,
                reduce_only=reduce_only
            )
            if "orderId" in data:
                oid = str(data["orderId"])
                self.logger.info(f"[{tag}] 成功 orderId={oid} status={data.get('status')}")
                asyncio.create_task(self._poll_and_notify(symbol, oid))
                return oid
            self.logger.error(f"[{tag}] 失败: {data.get('code')} {data.get('msg')}")
            return None
        except Exception as e:
            self.logger.error(f"[下单] 异常: {e}")
            return None

    async def get_order_status(self, symbol: str, order_id: str) -> str | None:
        try:
            data = await self._api_get_order(symbol, order_id)
            return data.get("status")
        except Exception as e:
            self.logger.error(f"[查单] 异常: {e}")
            return None

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        try:
            self.logger.info(f"[撤单] orderId={order_id}")
            data = await self._api_cancel_order(symbol, order_id)
            if data.get("status") == "CANCELED":
                self.logger.info(f"[撤单] 成功 orderId={order_id}")
                # 撤单也视为"完成"，通知等待方
                self.notify_fill(order_id)
            else:
                self.logger.error(f"[撤单] 失败: {data.get('code')} {data.get('msg')}")
        except Exception as e:
            self.logger.error(f"[撤单] 异常: {e}")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.info("HTTP Session 已关闭")

    # ─────────────────────────────────────────────────────
    # 轮询（模拟盘专用）
    # ─────────────────────────────────────────────────────

    async def _poll_and_notify(self, symbol: str, order_id: str) -> None:
        """轮询订单状态，成交/撤单后调用 notify_fill 唤醒等待方"""
        while True:
            await asyncio.sleep(2)
            status = await self.get_order_status(symbol, order_id)
            self.logger.info(f"[轮询] orderId={order_id} status={status}")
            if status in ("FILLED", "CANCELED", "EXPIRED"):
                self.notify_fill(order_id)
                return
