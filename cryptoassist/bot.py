"""บอทเทรดอัตโนมัติ: กลยุทธ์ MA crossover + ตัวกรอง RSI + stop-loss / take-profit.

โหมดเริ่มต้นคือ paper trading (จำลอง ไม่ใช้เงินจริง) ทุกการซื้อขายถูกบันทึกลงพอร์ต
ด้วย account='paper' หรือ 'live' เพื่อดูผลย้อนหลังได้
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .exchange import Exchange
from .indicators import crossover, ema, rsi
from .notifier import Notifier
from .portfolio import Portfolio

PAPER_FEE_RATE = 0.001  # 0.1% ใกล้เคียงค่าธรรมเนียม taker ทั่วไป


@dataclass
class BotSettings:
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    strategy: str = "ma_cross"
    fast: int = 9
    slow: int = 21
    rsi_period: int = 14
    rsi_buy_below: float = 70
    order_quote_amount: float = 50
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    max_position_quote: float = 500
    poll_seconds: int = 60
    paper_starting_quote: float = 1000

    def __post_init__(self):
        if self.fast >= self.slow:
            raise ValueError("fast ต้องน้อยกว่า slow")
        if self.order_quote_amount <= 0:
            raise ValueError("order_quote_amount ต้องมากกว่า 0")


class TradingBot:
    def __init__(self, settings: BotSettings, ex: Exchange, portfolio: Portfolio,
                 notifier: Notifier, live: bool = False):
        self.s, self.ex, self.pf, self.notifier, self.live = settings, ex, portfolio, notifier, live
        self.account = "live" if live else "paper"

    # ---------- state ----------
    def position(self):
        return self.pf.summary(self.account).positions.get(self.s.symbol.upper())

    def paper_cash(self) -> float:
        return self.s.paper_starting_quote + self.pf.summary("paper").quote_flow

    # ---------- signal ----------
    def signal(self, closes: list[float]) -> tuple[str | None, float | None]:
        x = crossover(ema(closes, self.s.fast), ema(closes, self.s.slow))
        r = rsi(closes, self.s.rsi_period)[-1]
        return x, r

    # ---------- orders ----------
    def _buy(self, price: float, reason: str) -> None:
        quote = self.s.order_quote_amount
        pos = self.position()
        held_value = (pos.amount * price) if pos else 0.0
        if held_value + quote > self.s.max_position_quote:
            self.notifier.send(f"ข้ามการซื้อ: เกินเพดาน max_position_quote ({self.s.max_position_quote})")
            return
        if self.live:
            o = self.ex.market_buy_quote(self.s.symbol, quote)
            amount = float(o.get("filled") or o["amount"])
            fill = float(o.get("average") or price)
            fee = float((o.get("fee") or {}).get("cost") or 0)
        else:
            if self.paper_cash() < quote:
                self.notifier.send(f"ข้ามการซื้อ: เงินจำลองไม่พอ ({self.paper_cash():.2f})")
                return
            fill, fee = price, quote * PAPER_FEE_RATE
            amount = (quote - fee) / fill
        self.pf.add_trade(self.s.symbol, "buy", amount, fill, fee, account=self.account,
                          exchange=self.ex.id, note=reason)
        self.notifier.send(f"[{self.account.upper()}] ซื้อ {amount:.6f} {self.s.symbol} @ {fill:,.4f} — {reason}")

    def _sell_all(self, price: float, reason: str) -> None:
        pos = self.position()
        if not pos or pos.amount <= 0:
            return
        amount = pos.amount
        if self.live:
            o = self.ex.market_sell(self.s.symbol, amount)
            amount = float(o.get("filled") or o["amount"])
            fill = float(o.get("average") or price)
            fee = float((o.get("fee") or {}).get("cost") or 0)
        else:
            fill, fee = price, amount * price * PAPER_FEE_RATE
        pnl = (fill - pos.avg_cost) * amount - fee
        self.pf.add_trade(self.s.symbol, "sell", amount, fill, fee, account=self.account,
                          exchange=self.ex.id, note=reason)
        self.notifier.send(f"[{self.account.upper()}] ขาย {amount:.6f} {self.s.symbol} @ {fill:,.4f} "
                           f"กำไร/ขาดทุน {pnl:+,.2f} — {reason}")

    # ---------- main loop ----------
    def step(self) -> str:
        """ทำงาน 1 รอบ คืนค่า action ที่ทำ: buy / sell / hold."""
        closes = self.ex.closes(self.s.symbol, self.s.timeframe, limit=max(self.s.slow, self.s.rsi_period) * 5)
        price = self.ex.price(self.s.symbol)
        pos = self.position()

        if pos and pos.amount > 0:
            change = (price / pos.avg_cost - 1) * 100
            if change <= -self.s.stop_loss_pct:
                self._sell_all(price, f"Stop-loss {change:.2f}%")
                return "sell"
            if change >= self.s.take_profit_pct:
                self._sell_all(price, f"Take-profit {change:+.2f}%")
                return "sell"

        cross, r = self.signal(closes)
        if cross == "death" and pos and pos.amount > 0:
            self._sell_all(price, "EMA death cross")
            return "sell"
        if cross == "golden" and (r is None or r < self.s.rsi_buy_below):
            if not (pos and pos.amount > 0):
                self._buy(price, f"EMA golden cross, RSI={r:.1f}" if r is not None else "EMA golden cross")
                return "buy"
        return "hold"

    def run(self, max_steps: int | None = None) -> None:
        mode = "🔴 LIVE (เงินจริง)" if self.live else "🧪 PAPER (จำลอง)"
        self.notifier.send(f"เริ่มบอท {mode} {self.s.symbol} {self.s.timeframe} "
                           f"EMA{self.s.fast}/{self.s.slow} SL {self.s.stop_loss_pct}% TP {self.s.take_profit_pct}%")
        n = 0
        while max_steps is None or n < max_steps:
            try:
                self.step()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.notifier.send(f"⚠️ บอทเจอข้อผิดพลาด (จะลองใหม่รอบหน้า): {e}")
            n += 1
            if max_steps is None or n < max_steps:
                time.sleep(self.s.poll_seconds)
