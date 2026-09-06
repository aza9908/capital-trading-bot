"""Small, dependency-free indicator helpers operating on plain float lists."""
from __future__ import annotations


def parse_bars(raw_prices: list[dict]) -> list[dict]:
    """Convert Capital.com's bid/ask price bars into plain mid-price OHLC dicts."""
    bars = []
    for p in raw_prices:
        def mid(field: str) -> float:
            side = p[field]
            return (side["bid"] + side["ask"]) / 2

        bars.append(
            {
                "time": p["snapshotTimeUTC"],
                "open": mid("openPrice"),
                "high": mid("highPrice"),
                "low": mid("lowPrice"),
                "close": mid("closePrice"),
            }
        )
    return bars


def sma(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running_sum = 0.0
    for i, v in enumerate(values):
        running_sum += v
        if i >= window:
            running_sum -= values[i - window]
        if i >= window - 1:
            result[i] = running_sum / window
    return result


def average_true_range(bars: list[dict], window: int = 14) -> float | None:
    """Simple ATR over the last `window` bars, used to size stop-loss distance."""
    if len(bars) < window + 1:
        return None
    true_ranges = []
    for i in range(1, len(bars)):
        high, low, prev_close = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    recent = true_ranges[-window:]
    return sum(recent) / len(recent)
