"""ตรวจตรรกะ "รอ BTC กลับขึ้นเหนือ EMA200 ก่อนซื้อ" ด้วยข้อมูลจริง.

คำถามจากเจ้าของ: ถ้าต้องรอ BTC ขึ้นอีก ~20% เราพลาดกำไรช่วงนั้นไปหรือเปล่า?
  1. เทียบตัวกรองตลาดหลายแบบบน champion (keltner_trend k=2, stop=3) ช่วง out-of-sample เดียวกับ Judge:
     ไม่มีตัวกรอง / EMA50 / EMA100 / EMA200 (ปัจจุบัน) / EMA200 ที่ชันขึ้น / BTC ทำ high ใหม่ 20 วัน
  2. ทุกครั้งที่ BTC ตัดขึ้นเหนือ EMA200 (4h) ในอดีต: ตอนนั้นขึ้นมาจากจุดต่ำสุดแล้วกี่ % (ส่วนที่ "พลาด")
     และหลังจากนั้นขึ้นต่ออีกกี่ % ใน 30/90 วัน (ส่วนที่ "ยังได้")
  3. เส้น EMA200 เองกำลังลดลงเร็วแค่ไหน — ระยะ +20% ไม่ได้คงที่

python -m lab.regime_research
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lab.data import ROOT, now_iso
from lab.engine import Signals, load_market, metrics, simulate
from lab.judge import FOLDS, idx
from lab.strategies import atr, ema


def keltner(m, regime: np.ndarray, k=2.0, stop=3.0) -> Signals:
    c = m.df("close"); a = atr(m, 20); mid = ema(c, 20)
    entry = (c > mid + k * a) & (c.shift(1) <= mid.shift(1) + k * a.shift(1)) & (c > ema(c, 200))
    e = entry.fillna(False).to_numpy() & regime
    return Signals(e, (a * stop).to_numpy(), exit=(c < mid).fillna(False).to_numpy(), trail_atr=(a * 3).to_numpy())


def main():
    m = load_market(); start = idx(m, FOLDS[0][1]); end = len(m.times)
    btc = m.df("close")["BTCUSDT"]; S = len(m.symbols)
    rep = lambda b: np.repeat(np.asarray(b, bool)[:, None], S, axis=1)
    e200 = ema(btc.to_frame(), 200)["BTCUSDT"]
    filters = {
        "none": ("ไม่มีตัวกรอง (ซื้อทุกสัญญาณ)", rep(np.ones(len(btc)))),
        "ema50": ("BTC เหนือ EMA50 (เร็ว)", rep(btc > ema(btc.to_frame(), 50)["BTCUSDT"])),
        "ema100": ("BTC เหนือ EMA100", rep(btc > ema(btc.to_frame(), 100)["BTCUSDT"])),
        "ema200": ("BTC เหนือ EMA200 (ปัจจุบัน)", rep(btc > e200)),
        "ema200_or_slope": ("BTC เหนือ EMA200 หรือ EMA50 ชันขึ้นและราคาเหนือ EMA50", rep((btc > e200) | ((btc > ema(btc.to_frame(), 50)["BTCUSDT"]) & (ema(btc.to_frame(), 50)["BTCUSDT"].diff(6) > 0)))),
        "hh20d": ("BTC ทำ high ใหม่ในรอบ 20 วัน (120 แท่ง) ภายใน 10 วันที่ผ่านมา", rep((btc >= btc.rolling(120).max()).rolling(60).max().fillna(0) > 0)),
    }
    rows = []
    for key, (label, reg) in filters.items():
        res = simulate(m, keltner(m, reg), start, end); mt = metrics(res); tr = res.trades
        rows.append({"filter": key, "label": label, "return_pct": round(mt["return"] * 100, 2), "sharpe": round(mt["sharpe"], 2),
                     "max_dd_pct": round(mt["max_dd"] * 100, 2), "trades": int(len(tr)), "win_pct": round(mt["win_rate"] * 100, 1),
                     "expectancy_r": round(mt["avg_r"], 3)})
    # BTC cross-above events (ทั้งประวัติที่มี)
    above = (btc > e200).to_numpy(); ev = []
    t = 1
    while t < len(btc):
        if above[t] and not above[t - 1]:
            lo_i = max(0, t - 360); low = float(btc.iloc[lo_i:t + 1].min())   # จุดต่ำสุด 60 วันก่อนหน้า
            p = float(btc.iloc[t])
            f30 = float(btc.iloc[min(len(btc) - 1, t + 180)] / p - 1) * 100; f90 = float(btc.iloc[min(len(btc) - 1, t + 540)] / p - 1) * 100
            hold = t
            while hold < len(btc) and above[hold]: hold += 1
            ev.append({"time": str(btc.index[t]), "price": round(p), "from_low_pct": round((p / low - 1) * 100, 1),
                       "next_30d_pct": round(f30, 1), "next_90d_pct": round(f90, 1), "stayed_above_days": round((hold - t) * 4 / 24, 1),
                       "complete": t + 540 < len(btc)})
            t = hold  # ข้ามจนกว่าจะหลุดลงมา
        t += 1
    real = [e for e in ev if e["stayed_above_days"] >= 3]   # ตัดการตัดขึ้นหลอกสั้นๆ ออกจากค่าเฉลี่ยหลัก
    e200_slope = float(e200.iloc[-1] / e200.iloc[-43] - 1) * 100  # ~7 วัน
    out = {"generated_at": now_iso(), "period": [str(m.times[start]), str(m.times[-1])], "filters": rows,
           "btc_now": round(float(btc.iloc[-1])), "ema200_now": round(float(e200.iloc[-1])), "gap_pct": round(float(e200.iloc[-1] / btc.iloc[-1] - 1) * 100, 1),
           "ema200_change_7d_pct": round(e200_slope, 2), "crosses": ev,
           "cross_stats": {"n": len(ev), "n_real": len(real),
                           "median_from_low_pct": float(np.median([e["from_low_pct"] for e in ev])) if ev else None,
                           "whipsaw_pct": round((1 - len(real) / len(ev)) * 100, 1) if ev else None}}
    (ROOT / "research" / "regime_research.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for r in rows: print(r)
    print("gap now", out["gap_pct"], "% · EMA200 7d change", out["ema200_change_7d_pct"], "%")
    for e in ev: print(e)
    print(out["cross_stats"])


if __name__ == "__main__":
    main()
