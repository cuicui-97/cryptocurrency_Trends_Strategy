"""
Binance U本位永续合约交易执行（REST API，HMAC-SHA256 签名）

分两层：
  _api_xxx()  — 底层，纯 HTTP 请求，只负责发请求返回原始数据
  业务方法()  — 上层，组合 API 调用，处理业务逻辑
"""

import asyncio
import hashlib
import hmac
import logging
import time

import aiohttp

import config
from core.base_trader import BaseTrader
from core.logger import make_logger


class BinanceTrader(BaseTrader):

    def __init__(self, api_key: str, secret_key: str,
                 order_timeout: int = config.ORDER_TIMEOUT,
                 log_file: str = config.TRADER_LOG_FILE):
        self.api_key = api_key
        self.secret_key = secret_key
        self.order_timeout = order_timeout
        self.base_url = config.REST_BASE_URL
        self._session: aiohttp.ClientSession | None = None
        self._init_logging(log_file)

    def _init_logging(self, log_file: str) -> None:
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
    # 底层 API（纯 HTTP 请求，返回原始 JSON）
    # ─────────────────────────────────────────────────────

    async def _api_get(self, path: str, params: str) -> dict:
        """发送 GET 请求"""
        url = f"{self.base_url}{path}?{params}&signature={self._sign(params)}"
        async with self._session.get(url) as resp:
            return await resp.json()

    async def _api_post(self, path: str, params: str) -> dict:
        """发送 POST 请求"""
        url = f"{self.base_url}{path}?{params}&signature={self._sign(params)}"
        async with self._session.post(url) as resp:
            return await resp.json()

    async def _api_delete(self, path: str, params: str) -> dict:
        """发送 DELETE 请求"""
        url = f"{self.base_url}{path}?{params}&signature={self._sign(params)}"
        async with self._session.delete(url) as resp:
            return await resp.json()

    # ─────────────────────────────────────────────────────
    # 账户接口
    # ─────────────────────────────────────────────────────

    async def _api_get_account(self) -> dict:
        params = f"timestamp={self._timestamp()}"
        return await self._api_get("/fapi/v2/account", params)

    async def _api_set_leverage(self, symbol: str, leverage: int) -> dict:
        params = f"symbol={symbol}&leverage={leverage}&timestamp={self._timestamp()}"
        return await self._api_post("/fapi/v1/leverage", params)

    async def _api_set_margin_type(self, symbol: str, margin_type: str) -> dict:
        params = f"symbol={symbol}&marginType={margin_type}&timestamp={self._timestamp()}"
        return await self._api_post("/fapi/v1/marginType", params)

    # ─────────────────────────────────────────────────────
    # 订单接口
    # ─────────────────────────────────────────────────────

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

    async def _api_get_order(self, symbol: str, order_id: int) -> dict:
        params = f"symbol={symbol}&orderId={order_id}&timestamp={self._timestamp()}"
        return await self._api_get("/fapi/v1/order", params)

    async def _api_cancel_order(self, symbol: str, order_id: int) -> dict:
        params = f"symbol={symbol}&orderId={order_id}&timestamp={self._timestamp()}"
        return await self._api_delete("/fapi/v1/order", params)

    # ─────────────────────────────────────────────────────
    # 业务方法（组合 API 调用，处理日志和错误）
    # ─────────────────────────────────────────────────────

    async def connect_and_login(self) -> None:
        """创建共享 Session，验证 API Key，初始化合约参数"""
        self._session = aiohttp.ClientSession(headers=self._headers())
        try:
            self.logger.info(f"正在验证 API Key，服务器: {self.base_url}")
            data = await self._api_get_account()
            if "totalWalletBalance" in data:
                self.logger.info(f"API Key 验证成功，账户余额: {data['totalWalletBalance']} USDT")
            else:
                self.logger.error(f"API Key 验证失败: {data}")
                return

            # 设置杠杆
            data = await self._api_set_leverage(config.SYMBOL, config.LEVERAGE)
            self.logger.info(f"杠杆设置: {data.get('leverage')}x")

            # 设置保证金模式（已是目标模式时会报错，忽略）
            data = await self._api_set_margin_type(config.SYMBOL, config.MARGIN_TYPE)
            if data.get("code") == 200 or "msg" in data:
                self.logger.info(f"保证金模式: {config.MARGIN_TYPE}")

        except Exception as e:
            self.logger.error(f"connect_and_login 失败: {e}")

    async def submit_limit_order(self, symbol: str, side: str,
                                 price: float, size: float,
                                 reduce_only: bool = False,
                                 post_only: bool = True) -> int | None:
        """
        提交限价单，返回 orderId。
        post_only=True  → GTX，只做 Maker
        post_only=False → GTC，允许 Taker（止损用）
        """
        try:
            tif = config.TIME_IN_FORCE if post_only else "GTC"
            tag = "平仓限价单" if reduce_only else "开仓限价单"
            self.logger.info(f"[{tag}] {side.upper()} price={price} size={size} tif={tif}")
            data = await self._api_submit_order(
                symbol=symbol, side=side, order_type=config.ORDER_TYPE,
                quantity=size, price=price, time_in_force=tif,
                reduce_only=reduce_only
            )
            if "orderId" in data:
                self.logger.info(f"[{tag}] 成功 orderId={data['orderId']} status={data.get('status')}")
                return data["orderId"]
            self.logger.error(f"[{tag}] 失败: code={data.get('code')} msg={data.get('msg')}")
            return None
        except Exception as e:
            self.logger.error(f"[下单] 异常: {e}")
            return None

    async def submit_market_order(self, symbol: str, side: str, size: float,
                                  reduce_only: bool = False) -> int | None:
        """提交市价单（用于止损平仓），返回 orderId。平仓时传 reduce_only=True"""
        try:
            tag = "平仓市价单" if reduce_only else "市价单"
            self.logger.info(f"[{tag}] {side.upper()} size={size}")
            data = await self._api_submit_order(
                symbol=symbol, side=side, order_type="MARKET",
                quantity=size, reduce_only=reduce_only
            )
            if "orderId" in data:
                self.logger.info(f"[{tag}] 成功 orderId={data['orderId']}")
                return data["orderId"]
            self.logger.error(f"[{tag}] 失败: code={data.get('code')} msg={data.get('msg')}")
            return None
        except Exception as e:
            self.logger.error(f"[{tag}] 异常: {e}")
            return None

    async def get_order_status(self, symbol: str, order_id: int) -> str | None:
        """查询订单状态，返回状态字符串"""
        try:
            data = await self._api_get_order(symbol, order_id)
            return data.get("status")
        except Exception as e:
            self.logger.error(f"[查单] 异常: {e}")
            return None

    async def cancel_order(self, symbol: str, order_id: int) -> None:
        """撤销订单"""
        try:
            self.logger.info(f"[撤单] orderId={order_id}")
            data = await self._api_cancel_order(symbol, order_id)
            if data.get("status") == "CANCELED":
                self.logger.info(f"[撤单] 成功 orderId={order_id}")
            else:
                self.logger.error(f"[撤单] 失败: code={data.get('code')} msg={data.get('msg')}")
        except Exception as e:
            self.logger.error(f"[撤单] 异常: {e}")

    async def place_limit_order(self, symbol: str, side: str,
                                price: float, size: float) -> None:
        """下限价单并在超时后自动撤单（BaseTrader 接口实现）"""
        _ = asyncio.create_task(self._process_order(symbol, side, price, size))

    async def _process_order(self, symbol: str, side: str,
                             price: float, size: float) -> None:
        order_id = await self.submit_limit_order(symbol, side, price, size)
        if order_id is None:
            return

        self.logger.info(f"[订单] 等待 {self.order_timeout}s 后检查状态...")
        await asyncio.sleep(self.order_timeout)

        status = await self.get_order_status(symbol, order_id)
        self.logger.info(f"[订单] {order_id} 状态: {status}")

        if status not in ("FILLED", "CANCELED", "EXPIRED"):
            self.logger.info(f"[订单] {order_id} 超时未成交，撤单")
            await self.cancel_order(symbol, order_id)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.info("HTTP Session 已关闭")
