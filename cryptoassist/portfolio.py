"""บันทึกการซื้อขาย (SQLite) และคำนวณพอร์ตแบบต้นทุนเฉลี่ย (average cost)."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    account TEXT NOT NULL DEFAULT 'manual',
    exchange TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    amount REAL NOT NULL CHECK (amount > 0),
    price REAL NOT NULL CHECK (price > 0),
    fee REAL NOT NULL DEFAULT 0,
    note TEXT DEFAULT ''
);
"""


@dataclass
class Position:
    symbol: str
    amount: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    trades: int = 0

    @property
    def cost_basis(self) -> float:
        return self.amount * self.avg_cost

    def unrealized(self, price: float) -> float:
        return (price - self.avg_cost) * self.amount


@dataclass
class Summary:
    positions: dict[str, Position] = field(default_factory=dict)
    quote_flow: float = 0.0  # เงิน quote สุทธิ (ขาย - ซื้อ - ค่าธรรมเนียม)


class Portfolio:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add_trade(self, symbol: str, side: str, amount: float, price: float, fee: float = 0.0,
                  account: str = "manual", exchange: str = "", note: str = "", ts: float | None = None) -> int:
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side ต้องเป็น buy หรือ sell")
        if amount <= 0 or price <= 0:
            raise ValueError("amount และ price ต้องมากกว่า 0")
        if side == "sell":
            held = self.summary(account).positions.get(symbol.upper(), Position(symbol)).amount
            if amount > held + 1e-12:
                raise ValueError(f"ขาย {amount} มากกว่าที่ถืออยู่ ({held}) ใน {symbol}")
        cur = self.db.execute(
            "INSERT INTO trades (ts, account, exchange, symbol, side, amount, price, fee, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts or time.time(), account, exchange, symbol.upper(), side, amount, price, fee, note),
        )
        self.db.commit()
        return cur.lastrowid

    def delete_trade(self, trade_id: int) -> bool:
        cur = self.db.execute("DELETE FROM trades WHERE id=?", (trade_id,))
        self.db.commit()
        return cur.rowcount > 0

    def trades(self, account: str | None = None, symbol: str | None = None) -> list[sqlite3.Row]:
        q, args = "SELECT * FROM trades WHERE 1=1", []
        if account:
            q += " AND account=?"
            args.append(account)
        if symbol:
            q += " AND symbol=?"
            args.append(symbol.upper())
        return self.db.execute(q + " ORDER BY ts, id", args).fetchall()

    def summary(self, account: str | None = None) -> Summary:
        s = Summary()
        for t in self.trades(account):
            p = s.positions.setdefault(t["symbol"], Position(t["symbol"]))
            p.trades += 1
            p.total_fees += t["fee"]
            value = t["amount"] * t["price"]
            if t["side"] == "buy":
                new_amt = p.amount + t["amount"]
                # ค่าธรรมเนียมตอนซื้อรวมเข้าต้นทุน
                p.avg_cost = (p.cost_basis + value + t["fee"]) / new_amt
                p.amount = new_amt
                s.quote_flow -= value + t["fee"]
            else:
                p.realized_pnl += (t["price"] - p.avg_cost) * t["amount"] - t["fee"]
                p.amount -= t["amount"]
                if p.amount < 1e-12:
                    p.amount, p.avg_cost = 0.0, 0.0
                s.quote_flow += value - t["fee"]
        return s
