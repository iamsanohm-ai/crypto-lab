"""Backtest engine แบบ portfolio (long-only spot) บนแท่ง 4h.

กติกากันการโกงตัวเอง:
  * สัญญาณคำนวณตอนแท่งปิด → เข้าซื้อที่ราคาเปิดของแท่งถัดไป (ไม่มี lookahead)
  * stop ถูกเช็คด้วย low ของแท่ง; ถ้าเปิดต่ำกว่า stop (gap) จะขายที่ราคาเปิด
  * ถ้าในแท่งเดียวกันโดนทั้ง stop และ target → ถือว่าโดน stop ก่อน (มองแง่ร้าย)
  * ค่าธรรมเนียม + slippage ทั้งขาเข้าและขาออก
  * เหรียญที่ถูกถอด/หยุดเทรดระหว่างถือ → ขายที่ราคาสุดท้ายหัก haircut 2%
  * เข้าได้เฉพาะเหรียญที่อยู่ใน universe เดือนนั้น (point-in-time)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from lab.data import DATA

BARS_PER_DAY = 6


@dataclass
class Market:
    times: pd.DatetimeIndex
    symbols: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    qvol: np.ndarray
    taker: np.ndarray
    funding: np.ndarray
    member: np.ndarray           # [T,S] bool: อยู่ใน universe เดือนนี้
    last_bar: np.ndarray         # [S] index ของแท่งสุดท้ายที่มีข้อมูล

    def df(self, name: str) -> pd.DataFrame:
        return pd.DataFrame(getattr(self, name), index=self.times, columns=self.symbols)


def load_market(exclude: set[str] = frozenset()) -> Market:
    uni = json.loads((DATA / "universe.json").read_text())
    syms = sorted({s for m in uni["members"].values() for s in m} - set(exclude))
    frames = {}
    for s in syms:
        p = DATA / "klines" / f"{s}.parquet"
        if p.exists():
            frames[s] = pd.read_parquet(p).set_index("time")
    syms = sorted(frames)
    times = pd.DatetimeIndex(sorted(set().union(*[f.index for f in frames.values()])))
    def mat(col):
        return pd.DataFrame({s: frames[s][col] for s in syms}).reindex(times).to_numpy(float)
    close = mat("close")
    fund = np.full_like(close, np.nan)
    for j, s in enumerate(syms):
        p = DATA / "funding" / f"{s}.parquet"
        if p.exists():
            f = pd.read_parquet(p).sort_values("time")
            f["time"] = f["time"].dt.as_unit("ns")
            # funding ที่ประกาศ ณ เวลา ts รู้แล้วตอนแท่งที่ปิดหลัง ts → ใช้ close time ของแท่ง
            close_times = pd.DataFrame({"t": (times + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)).as_unit("ns")})
            m = pd.merge_asof(close_times, f.rename(columns={"time": "t"}), on="t", direction="backward")
            fund[:, j] = m["funding"].to_numpy()
    member = np.zeros_like(close, dtype=bool)
    month_idx = times.strftime("%Y-%m")
    for month, mem in uni["members"].items():
        rows = month_idx == month
        for s in mem:
            if s in syms:
                member[rows, syms.index(s)] = True
    last_bar = np.array([np.max(np.where(~np.isnan(close[:, j]))[0]) for j in range(len(syms))])
    return Market(times, syms, mat("open"), mat("high"), mat("low"), close, mat("quote_volume"),
                  mat("taker_quote"), fund, member, last_bar)


@dataclass
class Costs:
    fee: float = 0.001        # 0.1% Binance spot taker มาตรฐาน
    slippage: float = 0.0005  # 0.05%
    delist_haircut: float = 0.02

    @property
    def per_side(self) -> float:
        return self.fee + self.slippage


@dataclass
class Risk:
    capital: float = 500.0
    risk_per_trade: float = 0.005   # 0.5%
    max_positions: int = 5
    max_position_frac: float = 0.25
    min_notional: float = 5.0


@dataclass
class Signals:
    """ผลลัพธ์จากกลยุทธ์ (ทุก matrix ขนาด [T,S] คำนวณจากข้อมูล ณ แท่งปิด)."""
    entry: np.ndarray                 # bool
    stop_dist: np.ndarray             # ระยะ stop เป็นราคา (เช่น 2*ATR)
    exit: np.ndarray | None = None    # bool: ออกที่ open แท่งถัดไป
    target_r: float | None = None     # take profit เป็นจำนวนเท่าของระยะ stop
    max_hold: int | None = None       # จำนวนแท่งสูงสุด
    trail_atr: np.ndarray | None = None  # ถ้ามี: trailing stop = highest close - trail
    score: np.ndarray | None = None   # ใช้จัดลำดับเมื่อมีสัญญาณพร้อมกันหลายเหรียญ


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    meta: dict = field(default_factory=dict)


def simulate(m: Market, sig: Signals, start: int, end: int, costs: Costs = Costs(), risk: Risk = Risk()) -> Result:
    T, S = m.close.shape
    cash = risk.capital
    pos: dict[int, dict] = {}
    eq = np.empty(end - start)
    trades = []
    c = costs.per_side
    score = sig.score if sig.score is not None else np.nan_to_num(m.qvol)

    def close_pos(j, t, price, reason):
        nonlocal cash
        p = pos.pop(j)
        proceeds = p["qty"] * price * (1 - c)
        cash += proceeds
        trades.append({"symbol": m.symbols[j], "entry_time": m.times[p["t"]], "exit_time": m.times[t],
                       "entry": p["entry"], "exit": price, "qty": p["qty"], "cost": p["cost"],
                       "pnl": proceeds - p["cost"], "r": (proceeds - p["cost"]) / p["risk"],
                       "bars": t - p["t"], "reason": reason})

    for t in range(start, end):
        # 1) เข้าซื้อจากสัญญาณของแท่งก่อนหน้า ที่ราคาเปิดแท่งนี้
        if t > 0 and len(pos) < risk.max_positions:
            cand = np.where(sig.entry[t - 1] & m.member[t - 1] & ~np.isnan(m.open[t]))[0]
            cand = [j for j in cand if j not in pos]
            cand.sort(key=lambda j: -np.nan_to_num(score[t - 1, j], nan=-np.inf))
            equity_now = cash + sum(p["qty"] * m.close[t - 1, j] for j, p in pos.items() if not np.isnan(m.close[t - 1, j]))
            for j in cand:
                if len(pos) >= risk.max_positions:
                    break
                px, dist = m.open[t, j], sig.stop_dist[t - 1, j]
                if not (dist > 0) or dist >= px:
                    continue
                risk_amt = equity_now * risk.risk_per_trade
                notional = min(risk_amt / (dist / px), equity_now * risk.max_position_frac, cash / (1 + c))
                if notional < risk.min_notional:
                    continue
                qty = notional / px
                cost = notional * (1 + c)
                cash -= cost
                pos[j] = {"t": t, "entry": px, "qty": qty, "cost": cost, "stop": px - dist,
                          "target": px + sig.target_r * dist if sig.target_r else None,
                          "risk": qty * dist + 2 * c * notional, "hi": px}
        # 2) จัดการสถานะที่ถืออยู่
        for j in list(pos):
            p = pos[j]
            if np.isnan(m.close[t, j]):
                if t > m.last_bar[j]:  # ถูกถอด
                    lb = m.last_bar[j]
                    close_pos(j, t, m.close[lb, j] * (1 - costs.delist_haircut), "delisted")
                continue
            o, h, l = m.open[t, j], m.high[t, j], m.low[t, j]
            if sig.exit is not None and t > p["t"] and sig.exit[t - 1, j]:
                close_pos(j, t, o, "signal"); continue
            if sig.max_hold and t - p["t"] >= sig.max_hold:
                close_pos(j, t, o, "time"); continue
            if l <= p["stop"]:
                close_pos(j, t, min(o, p["stop"]), "stop"); continue
            if p["target"] and h >= p["target"]:
                close_pos(j, t, max(o, p["target"]), "target"); continue
            if sig.trail_atr is not None:
                p["hi"] = max(p["hi"], m.close[t, j])
                tr = sig.trail_atr[t, j]
                if tr > 0:
                    p["stop"] = max(p["stop"], p["hi"] - tr)
        eq[t - start] = cash + sum(p["qty"] * (m.close[t, j] if not np.isnan(m.close[t, j]) else p["entry"])
                                   for j, p in pos.items())
    # ปิดทุกสถานะตอนจบช่วงทดสอบ (ไม่ให้กำไรค้างนับเป็นผลงาน)
    for j in list(pos):
        lb = min(end - 1, m.last_bar[j])
        close_pos(j, end - 1, m.close[lb, j], "end")
    eq[-1] = cash
    return Result(pd.Series(eq, index=m.times[start:end]), pd.DataFrame(trades))


# ---------------- metrics ----------------
def metrics(res: Result) -> dict:
    e = res.equity
    tr = res.trades
    ret = e.iloc[-1] / e.iloc[0] - 1 if len(e) else 0
    dd = (e / e.cummax() - 1).min() if len(e) else 0
    daily = e.resample("1D").last().pct_change().dropna()
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else 0.0
    monthly = e.resample("ME").last()
    mret = monthly.pct_change()
    if len(monthly):
        mret.iloc[0] = monthly.iloc[0] / e.iloc[0] - 1
    streak = cur = 0
    if len(tr):
        for pnl in tr.sort_values("exit_time")["pnl"]:
            cur = cur + 1 if pnl <= 0 else 0
            streak = max(streak, cur)
    return {
        "return": float(ret), "max_dd": float(dd), "sharpe": float(sharpe),
        "calmar": float(ret / abs(dd)) if dd < 0 else float("inf") if ret > 0 else 0.0,
        "trades": int(len(tr)), "win_rate": float((tr["pnl"] > 0).mean()) if len(tr) else 0.0,
        "avg_r": float(tr["r"].mean()) if len(tr) else 0.0,
        "profit_factor": float(tr.loc[tr.pnl > 0, "pnl"].sum() / -tr.loc[tr.pnl <= 0, "pnl"].sum())
        if len(tr) and (tr.pnl <= 0).any() else float("nan"),
        "worst_month": float(mret.min()) if len(mret) else 0.0,
        "worst_month_label": str(mret.idxmin().strftime("%Y-%m")) if len(mret) else "",
        "longest_losing_streak": int(streak),
        "exposure": float((res.trades["bars"].sum() / max(len(e), 1))) if len(tr) else 0.0,
    }
