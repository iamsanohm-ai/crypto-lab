"""Technical indicators (pure Python, ไม่ต้องใช้ pandas)."""
from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be > 0")
    window = 0.0
    for i, v in enumerate(values):
        window += v
        if i >= period:
            window -= values[i - period]
        if i >= period - 1:
            out[i] = window / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """RSI แบบ Wilder's smoothing."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / period, losses / period

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100 - 100 / (1 + g / l)

    out[period] = _rsi(avg_g, avg_l)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
        out[i] = _rsi(avg_g, avg_l)
    return out


def crossover(fast: list[float | None], slow: list[float | None]) -> str | None:
    """คืน 'golden' ถ้าเส้นเร็วตัดขึ้นในแท่งล่าสุด, 'death' ถ้าตัดลง, ไม่งั้น None."""
    if len(fast) < 2 or None in (fast[-1], fast[-2], slow[-1], slow[-2]):
        return None
    if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
        return "golden"
    if fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
        return "death"
    return None
