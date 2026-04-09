"""
信号生成器

负责接收成交数据，计算市场强度，判断开多/开空/无信号。
"""

import config


class SignalGenerator:

    def __init__(self,
                 window_size: int = config.WINDOW_SIZE,
                 threshold_long: float = config.THRESHOLD_LONG,
                 threshold_short: float = config.THRESHOLD_SHORT):
        self.window_size = window_size
        self.threshold_long = threshold_long
        self.threshold_short = threshold_short
        self._size_list: list[float] = []
        self.last_intensity: float = 0.0

    def add_trade(self, trade: dict) -> None:
        size = float(trade['sz'])
        self._size_list.append(size if trade['side'] == 'buy' else -size)
        if len(self._size_list) >= self.window_size:
            self._calculate()

    def _calculate(self) -> None:
        self.last_intensity = sum(self._size_list) / len(self._size_list)
        self._size_list.clear()

    def is_window_complete(self, trade_count: int) -> bool:
        """判断当前是否完成一个窗口"""
        return trade_count % self.window_size == 0

    def get_signal(self) -> str | None:
        """
        返回信号方向：
          'buy'  → 买方占优，开多
          'sell' → 卖方占优，开空
          None   → 无信号
        """
        if self.last_intensity > self.threshold_long:
            return "buy"
        elif self.last_intensity < self.threshold_short:
            return "sell"
        return None
