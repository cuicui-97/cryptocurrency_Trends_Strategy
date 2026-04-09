# ── 交易标的 ──────────────────────────────────────────────
SYMBOL = "BTCUSDT"

# ── 策略参数 ──────────────────────────────────────────────
# 每 WINDOW_SIZE 笔成交计算一次市场强度
WINDOW_SIZE = 30
# 买方强度 > THRESHOLD_LONG  → 开多
THRESHOLD_LONG = 0.05
# 卖方强度 < THRESHOLD_SHORT → 开空（负值）
THRESHOLD_SHORT = -0.05

# ── 合约参数 ──────────────────────────────────────────────
LEVERAGE = 1             # 杠杆倍数
MARGIN_TYPE = "ISOLATED" # 保证金模式：逐仓

# ── 下单参数 ──────────────────────────────────────────────
ORDER_SIZE = 0.003       # 每次下单数量（BTC），合约最小名义价值 100 USDT
TICK_SIZE = 0.1          # BTCUSDT 最小价格变动单位
ORDER_TIMEOUT = 10       # 挂单超时秒数，超时后检查状态
ORDER_TYPE = "LIMIT"     # 合约限价单（合约不支持 LIMIT_MAKER，用 GTX 替代）
TIME_IN_FORCE = "GTX"    # GTX = Post Only，只做 Maker
SPREAD = 0.0005          # 平仓目标价差（0.05%）
STOP_LOSS = 0.0008       # 止损比例（0.08%）

# ── 运行控制 ──────────────────────────────────────────────
# 处理 MAX_MESSAGES 笔成交后停止（None 表示持续运行）
MAX_MESSAGES = 1800

# ── REST API & WebSocket ──────────────────────────────────
REST_BASE_URL = "https://testnet.binancefuture.com"   # 合约测试网
WS_BASE_URL   = "wss://fstream.binancefuture.com"     # 合约测试网行情

# ── 日志文件 ──────────────────────────────────────────────
TRADE_LOG_FILE      = "logs/trade_data.log"   # 逐笔成交数据
ORDER_BOOK_LOG_FILE = "logs/order_book.log"   # 订单簿数据
TRADER_LOG_FILE     = "logs/trader_info.log"  # 策略信号、下单、持仓
