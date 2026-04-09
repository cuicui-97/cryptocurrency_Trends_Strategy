"""
盈亏追踪器

记录每笔交易的盈亏，提供统计分析。
"""

import config
from core.logger import make_logger
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TradeRecord:
    side: str           # 开仓方向：buy / sell
    entry_price: float  # 开仓价
    exit_price: float   # 平仓价
    size: float         # 数量
    pnl: float          # 盈亏（USDT）
    result: str         # 'take_profit' / 'stop_loss'
    timestamp: str      # 平仓时间


class PnlTracker:

    def __init__(self):
        self._records: list[TradeRecord] = []
        self.logger = make_logger(__name__, config.TRADER_LOG_FILE)

    def record(self, side: str, entry_price: float, exit_price: float,
               size: float, result: str) -> float:
        """
        记录一笔交易，返回本笔盈亏。

        :param result: 'take_profit' 或 'stop_loss'
        """
        pnl = self._calc_pnl(side, entry_price, exit_price, size)
        record = TradeRecord(
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            result=result,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self._records.append(record)
        self.logger.info(
            f"[盈亏] {result} side={side} entry={entry_price} "
            f"exit={exit_price} pnl={pnl:+.4f} USDT | "
            f"累计盈亏={self.total_pnl():+.4f} 胜率={self.win_rate():.1%} "
            f"交易次数={self.trade_count()}"
        )
        return pnl

    # ─────────────────────────────────────────────────────
    # 统计方法
    # ─────────────────────────────────────────────────────

    def total_pnl(self) -> float:
        """总盈亏（USDT）"""
        return round(sum(r.pnl for r in self._records), 4)

    def win_rate(self) -> float:
        """胜率（止盈次数 / 总次数）"""
        if not self._records:
            return 0.0
        wins = sum(1 for r in self._records if r.result == "take_profit")
        return wins / len(self._records)

    def trade_count(self) -> int:
        """总交易次数"""
        return len(self._records)

    def avg_pnl(self) -> float:
        """平均每笔盈亏"""
        if not self._records:
            return 0.0
        return round(self.total_pnl() / self.trade_count(), 4)

    def max_drawdown(self) -> float:
        """最大回撤（从历史最高累计盈亏到最低点的最大跌幅）"""
        if not self._records:
            return 0.0
        peak = 0.0
        max_dd = 0.0
        cumulative = 0.0
        for r in self._records:
            cumulative += r.pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 4)

    def summary(self) -> str:
        """输出统计摘要"""
        return (
            f"交易次数={self.trade_count()} "
            f"总盈亏={self.total_pnl():+.4f} USDT "
            f"胜率={self.win_rate():.1%} "
            f"平均盈亏={self.avg_pnl():+.4f} USDT "
            f"最大回撤={self.max_drawdown():.4f} USDT"
        )

    # ─────────────────────────────────────────────────────
    # 计算
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _calc_pnl(side: str, entry: float, exit_price: float, size: float) -> float:
        if side == "buy":
            return round((exit_price - entry) * size, 4)
        else:
            return round((entry - exit_price) * size, 4)
