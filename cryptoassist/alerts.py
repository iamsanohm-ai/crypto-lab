"""ระบบแจ้งเตือนราคาและสัญญาณเทคนิค.

ตัวอย่างกฎใน config.yaml:
  - {symbol: BTC/USDT, type: price_above, value: 120000}
  - {symbol: BTC/USDT, type: price_below, value: 90000}
  - {symbol: ETH/USDT, type: change_24h_above, value: 5}     # % เปลี่ยนแปลง 24 ชม.
  - {symbol: ETH/USDT, type: change_24h_below, value: -5}
  - {symbol: ETH/USDT, type: rsi_below, value: 30, timeframe: 1h, period: 14}
  - {symbol: ETH/USDT, type: rsi_above, value: 70, timeframe: 1h}
  - {symbol: BTC/USDT, type: ma_cross, fast: 50, slow: 200, timeframe: 4h}
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .exchange import Exchange
from .indicators import crossover, rsi, sma
from .notifier import Notifier

VALID_TYPES = {"price_above", "price_below", "change_24h_above", "change_24h_below",
               "rsi_above", "rsi_below", "ma_cross"}


@dataclass
class AlertRule:
    symbol: str
    type: str
    value: float | None = None
    timeframe: str = "1h"
    period: int = 14
    fast: int = 50
    slow: int = 200
    active: bool = field(default=False, init=False)  # กำลังอยู่ในสถานะ "แจ้งไปแล้ว"

    def __post_init__(self):
        if self.type not in VALID_TYPES:
            raise ValueError(f"ไม่รู้จักชนิดแจ้งเตือน '{self.type}' (ใช้ได้: {', '.join(sorted(VALID_TYPES))})")
        if self.type != "ma_cross" and self.value is None:
            raise ValueError(f"กฎ {self.type} ของ {self.symbol} ต้องมี value")

    def describe(self) -> str:
        if self.type == "ma_cross":
            return f"{self.symbol} MA{self.fast}/MA{self.slow} cross ({self.timeframe})"
        return f"{self.symbol} {self.type} {self.value}"


def evaluate(rule: AlertRule, ex: Exchange) -> str | None:
    """คืนข้อความถ้าเงื่อนไขเป็นจริงตอนนี้ ไม่งั้น None."""
    t = rule.type
    if t in ("price_above", "price_below"):
        p = ex.price(rule.symbol)
        hit = p > rule.value if t == "price_above" else p < rule.value
        return f"{rule.symbol} ราคา {p:,.4f} {'สูงกว่า' if t == 'price_above' else 'ต่ำกว่า'} {rule.value:,}" if hit else None
    if t.startswith("change_24h"):
        pct = ex.ticker(rule.symbol).get("percentage")
        if pct is None:
            return None
        hit = pct > rule.value if t.endswith("above") else pct < rule.value
        return f"{rule.symbol} เปลี่ยนแปลง 24 ชม. {pct:+.2f}% (เกณฑ์ {rule.value:+}%)" if hit else None
    if t in ("rsi_above", "rsi_below"):
        closes = ex.closes(rule.symbol, rule.timeframe, limit=rule.period * 10)
        r = rsi(closes, rule.period)[-1]
        if r is None:
            return None
        hit = r > rule.value if t == "rsi_above" else r < rule.value
        return f"{rule.symbol} RSI({rule.period}, {rule.timeframe}) = {r:.1f} {'>' if t == 'rsi_above' else '<'} {rule.value}" if hit else None
    if t == "ma_cross":
        closes = ex.closes(rule.symbol, rule.timeframe, limit=rule.slow + 5)
        x = crossover(sma(closes, rule.fast), sma(closes, rule.slow))
        if x == "golden":
            return f"{rule.symbol} 📈 Golden cross MA{rule.fast} ตัดขึ้น MA{rule.slow} ({rule.timeframe})"
        if x == "death":
            return f"{rule.symbol} 📉 Death cross MA{rule.fast} ตัดลง MA{rule.slow} ({rule.timeframe})"
        return None
    return None


class AlertEngine:
    """แจ้งเตือนครั้งเดียวตอนเงื่อนไขเริ่มเป็นจริง แล้วรอจนเงื่อนไขหายไปก่อนจะแจ้งซ้ำ (ไม่สแปม)."""

    def __init__(self, rules: list[AlertRule], ex: Exchange, notifier: Notifier):
        self.rules, self.ex, self.notifier = rules, ex, notifier

    @classmethod
    def from_config(cls, items: list[dict], ex: Exchange, notifier: Notifier) -> "AlertEngine":
        return cls([AlertRule(**item) for item in items], ex, notifier)

    def check_once(self) -> list[str]:
        fired = []
        for rule in self.rules:
            try:
                msg = evaluate(rule, self.ex)
            except Exception as e:
                self.notifier.send(f"⚠️ ตรวจ {rule.describe()} ไม่สำเร็จ: {e}")
                continue
            if msg and not rule.active:
                rule.active = True
                self.notifier.send(msg)
                fired.append(msg)
            elif not msg:
                rule.active = False
        return fired
