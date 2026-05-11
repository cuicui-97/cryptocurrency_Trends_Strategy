# 加密货币趋势策略回测系统

基于事件驱动的高性能回测引擎，支持策略回测与模拟盘交易。

## 项目特点

- **事件驱动架构**：基于 `asyncio` 的异步消息处理，支持高并发数据流
- **撮合引擎**：自研订单簿与撮合逻辑，支持 GTC/GTX/IOC/FOK/MARKET 订单类型
- **模块化设计**：配置、核心、策略、回测、实盘完全解耦
- **类型安全**：全类型注解，支持 IDE 自动补全与静态检查

## 项目结构

```
cryptocurrency/
├── config/              # 统一配置管理
│   ├── base.py         # 基础配置类
│   ├── backtest.py     # 回测配置
│   ├── strategy.py     # 策略配置
│   └── live.py         # 实盘配置
├── core/                # 核心抽象层
│   ├── exchange.py     # 交易所接口 (原 BaseTrader)
│   ├── data_feed.py    # 数据馈送接口 (原 BaseDataFetcher)
│   └── types.py        # 类型定义
├── matching/            # 撮合引擎
│   ├── matcher.py      # 统一入口
│   └── core/           # 核心实现
│       ├── engine.py   # 撮合逻辑
│       ├── order_book.py
│       ├── order.py
│       └── trade.py
├── backtest/            # 回测实现
│   ├── exchange.py     # BacktestExchange
│   └── data_feed.py    # BacktestDataFeed
├── strategy/            # 策略层
│   ├── runner.py       # 策略运行器
│   ├── signal_generator.py
│   ├── order_executor.py
│   └── pnl_tracker.py
└── scripts/             # 入口脚本
    ├── run_backtest.py
    ├── run_live.py
    └── collect_data.py
```

## 快速开始

### 环境准备

```bash
# 使用 uv 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate
```

### 运行回测

```bash
cd scripts
uv run python run_backtest.py

# 指定数据文件
uv run python run_backtest.py \
    --trades ../backtest/data/aggTrades/BTCUSDT-aggTrades-2026-04-12.csv \
    --book ../backtest/data/bookDepth/BTCUSDT-bookDepth-2026-04-12.csv
```

### 数据采集

```bash
uv run python scripts/collect_data.py
```

## 配置说明

配置文件位于 `config/` 目录，使用 dataclass 管理：

```python
# config/base.py
@dataclass(frozen=True)
class TradingConfig:
    symbol: str = "BTCUSDT"
    order_size: float = 0.003

@dataclass(frozen=True)
class SignalConfig:
    window_size: int = 30
    threshold_long: float = 0.05
    threshold_short: float = -0.05
```

使用方式：

```python
from config import STRATEGY_CONFIG, BACKTEST_CONFIG

print(STRATEGY_CONFIG.window_size)      # 30
print(BACKTEST_CONFIG.playback_speed)   # 0.0
```

## 撮合引擎

### 支持的订单类型

| 类型 | 全称 | 行为 |
|------|------|------|
| GTC | Good Till Cancel | 挂单直到成交或撤单 |
| GTX | Post Only | 若会立即成交则拒绝，只做 Maker |
| IOC | Immediate Or Cancel | 立即成交，剩余取消 |
| FOK | Fill Or Kill | 必须完全成交，否则全部取消 |
| MARKET | 市价单 | 逐档成交，剩余取消 |

### 使用示例

```python
from matching import Matcher

matcher = Matcher()

# 挂限价单
result = matcher.place_order(
    symbol="BTCUSDT",
    side="SELL",
    order_type="LIMIT",
    quantity=0.5,
    price=50000,
    time_in_force="GTC"
)

# 查询订单簿
ob = matcher.get_order_book("BTCUSDT", depth=5)
print(f"买一: {ob['best_bid']}, 卖一: {ob['best_ask']}")
```

## 回测原理

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 历史数据    │────▶│ 撮合引擎    │────▶│ 策略决策    │
│ (CSV)       │     │ (IOC驱动)   │     │ (信号生成)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
                                                ▼
                                        ┌─────────────┐
                                        │ 订单执行    │
                                        │ (止盈止损)  │
                                        └─────────────┘
```

1. **数据回放**：从 CSV 读取 aggTrades 和 bookDepth
2. **订单簿同步**：用最近快照维护市场深度
3. **撮合驱动**：每笔 aggTrade 提交 IOC 单触发撮合
4. **策略响应**：成交数据推送给策略，生成信号后下单

## 开发计划

- [x] 撮合引擎核心
- [x] 回测框架
- [x] 基础趋势策略
- [ ] 更多订单类型（止损单、条件单）
- [ ] 实盘交易接口（Binance）
- [ ] 性能优化（Cython/Rust 核心）
- [ ] Web 界面可视化

## 许可证

MIT
