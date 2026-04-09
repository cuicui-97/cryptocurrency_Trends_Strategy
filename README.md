# Cryptocurrency Intensity Strategy

基于市场强度信号的 BTC U本位永续合约趋势策略，通过 Binance WebSocket 实时采集成交数据，计算买卖双方力量对比，在明显趋势出现时自动开仓，止盈止损自动平仓。

---

## 策略原理

每积累 `WINDOW_SIZE`（默认 30）笔成交，计算有符号数量均值：

```
intensity = sum(signed_size) / window_size

其中：买单 → +size，卖单 → -size
```

- `intensity > THRESHOLD_LONG（0.05）` → 买方占优，市价**开多**
- `intensity < THRESHOLD_SHORT（-0.05）` → 卖方占优，市价**开空**
- 开仓后同时挂止盈单（GTX Post Only）和止损单（GTC），任意触发后撤掉另一笔

---

## 项目结构

```
cryptocurrency/
├── run.py                          # 入口文件
├── config.py                       # 全局配置参数
├── core/
│   ├── base_data_fetcher.py        # 行情采集抽象基类
│   ├── base_trader.py              # 交易执行抽象基类
│   └── logger.py                   # 统一日志工厂
├── exchange/
│   └── binance/
│       ├── data_fetcher.py         # Binance 行情采集（WebSocket）
│       └── trader.py               # Binance 交易执行（REST API）
└── strategy/
    ├── engine.py                   # 策略引擎，协调各模块
    ├── signal_generator.py         # 市场强度信号计算
    ├── order_executor.py           # 完整交易生命周期（开仓+平仓）
    └── pnl_tracker.py              # 盈亏统计
```

---

## 快速开始

### 1. 安装依赖

```bash
conda activate py312
pip install websockets aiohttp python-dotenv
```

### 2. 申请合约测试网 API Key

前往 [testnet.binancefuture.com](https://testnet.binancefuture.com) 用 GitHub 账号登录，免费申请合约测试网 Key。

### 3. 配置环境变量

创建 `.env` 文件：

```
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key
```

### 4. 启动

```bash
python run.py
```

---

## 主要参数（config.py）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `SYMBOL` | `BTCUSDT` | 交易对 |
| `WINDOW_SIZE` | `30` | 每积累多少笔成交计算一次市场强度 |
| `THRESHOLD_LONG` | `0.05` | 开多阈值 |
| `THRESHOLD_SHORT` | `-0.05` | 开空阈值 |
| `ORDER_SIZE` | `0.003` | 每次下单数量（BTC），约 200 USDT |
| `SPREAD` | `0.0005` | 止盈价差（0.05%） |
| `STOP_LOSS` | `0.0008` | 止损比例（0.08%） |
| `LEVERAGE` | `1` | 杠杆倍数 |
| `MARGIN_TYPE` | `ISOLATED` | 保证金模式：逐仓 |

---

## 日志

| 文件 | 内容 |
|---|---|
| `logs/trade_data.log` | 每笔成交原始数据 |
| `logs/order_book.log` | 订单簿快照（每50次记录一次） |
| `logs/trader_info.log` | 策略信号、开仓、平仓、盈亏统计 |

---

## 实测结果（合约测试网）

5 分钟内 16 笔交易：

| 指标 | 数值 |
|---|---|
| 胜率 | 62.5% |
| 总盈亏 | +0.04 USDT |
| 最大回撤 | 0.47 USDT |
| 止盈 | +0.107 USDT / 笔 |
| 止损 | -0.171 USDT / 笔 |

---

## 注意事项

- 当前连接 Binance **合约测试网**，不涉及真实资金
- 切换正式环境需修改 `config.py` 中的 `REST_BASE_URL` 和 `WS_BASE_URL`
- `.env` 已加入 `.gitignore`，API Key 不会提交到 git
- 大单会主导市场强度均值，极端行情下信号可能失真，建议上线前做充分回测
