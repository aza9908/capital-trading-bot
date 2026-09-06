"""SMA crossover strategy with a volatility-confirmed entry filter.

Deliberately simple and easy to backtest honestly, rather than clever.
Signal is based on closed bars only -- never peeks at the still-forming bar.

The filter: a raw SMA crossover fires on any cross, including tiny,
noisy ones inside a flat/choppy market -- that's the main source of the
low win rates seen in early backtests (lots of small losing whipsaws).
Requiring the crossover gap to be a meaningful fraction of recent ATR
rejects those marginal signals and only acts on more decisive moves.
This trades fewer signals for (hopefully) higher-quality ones -- confirm
with a backtest, don't just trust the theory.
"""
from __future__ import annotations

from dataclasses import dataclass

from indicators import average_true_range, sma


@dataclass
class SmaCrossoverStrategy:
    short_window: int = 20
    long_window: int = 50
    atr_window: int = 14
    min_separation_atr_multiplier: float = 0.02

    def __post_init__(self) -> None:
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window")

    def min_bars_required(self) -> int:
        return max(self.long_window + 2, self.atr_window + 1)

    def generate_signal(self, bars: list[dict]) -> str:
        """Returns "BUY", "SELL", or "HOLD" based on the most recently closed crossover.

        `bars` are dicts with at least open/high/low/close (see indicators.parse_bars).
        """
        if len(bars) < self.min_bars_required():
            return "HOLD"

        closes = [b["close"] for b in bars]
        short_sma = sma(closes, self.short_window)
        long_sma = sma(closes, self.long_window)

        prev_short, prev_long = short_sma[-2], long_sma[-2]
        curr_short, curr_long = short_sma[-1], long_sma[-1]

        if None in (prev_short, prev_long, curr_short, curr_long):
            return "HOLD"

        crossed_up = prev_short <= prev_long and curr_short > curr_long
        crossed_down = prev_short >= prev_long and curr_short < curr_long

        if not (crossed_up or crossed_down):
            return "HOLD"

        atr = average_true_range(bars, self.atr_window)
        if atr:
            separation = abs(curr_short - curr_long)
            if separation < atr * self.min_separation_atr_multiplier:
                return "HOLD"  # crossover too marginal relative to recent volatility -- likely noise

        return "BUY" if crossed_up else "SELL"
