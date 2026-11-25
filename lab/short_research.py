"""ศึกษาการเทรดระยะสั้น (ถือไม่กี่ชั่วโมงถึง 2 วัน) บนแท่ง 1 ชั่วโมงจริงของ Binance ย้อนหลัง 365 วัน.

แนวคิดที่ทดสอบ (มาจากงานวิจัย/แนวปฏิบัติที่มีหลักฐาน — ดู research/LITERATURE.md):
  trend_pullback  : ซื้อตอนย่อสั้นๆ (RSI3 ต่ำ) ในขาขึ้น 1h (EMA50 > EMA200)        — "buy the dip in an uptrend"
  range_breakout  : ทะลุจุดสูงสุด N ชั่วโมงพร้อม volume พุ่ง ในขาขึ้น                — intraday time-series momentum
  vol_breakout    : ราคาขึ้นเกิน ราคาเปิดวัน + k×ATR (Larry Williams volatility breakout)
  dip_reversal    : ร่วงแรงใน 24 ชม. (≤ −X%) แล้วซื้อรอเด้ง (short-term reversal)
ตัวกรองตลาดเพิ่มได้: BTC 1h อยู่เหนือ EMA200 (btc=True)
ค่าใช้จ่ายจริง: ค่าธรรมเนียม 0.1% + slippage 0.05% ต่อข้าง (ไปกลับ 0.30%)
เลือกพารามิเตอร์จาก 8 เดือนแรก (in-sample) แล้ววัดผล 4 เดือนล่าสุดที่ไม่เคยเห็น (out-of-sample) — ถือว่าผ่านเมื่อ OOS เฉลี่ยเป็นบวกหลังค่าธรรมเนียม

python -m lab.short_research
"""
from __future__ import annotations

import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from lab.data import DATA, ROOT, klines, now_iso
from lab.scalp_research import COINS, FEE, SLIP, ema, rsi, run, stats

DAYS, OOS_DAYS = 365, 120
CACHE = DATA / "scalp"; CACHE.mkdir(parents=True, exist_ok=True)


def load1h(sym: str) -> pd.DataFrame:
    f = CACHE / f"{sym}USDT_1h.parquet"
    end = int(time.time() // 3600 * 3600 * 1000)
    if f.exists():
        df = pd.read_parquet(f)
        if end - int(df["time"].iloc[-1].timestamp() * 1000) < 6 * 3600 * 1000:
            return df
    df = klines(f"{sym}USDT", "1h", end - DAYS * 86400 * 1000, end)
    df.to_parquet(f)
    return df


def atr(df, n=24):
    h, l, c = df.high, df.low, df.close
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().to_numpy()


def signals1h(df: pd.DataFrame, name: str, p: dict, btc_up: np.ndarray | None) -> np.ndarray:
    c, h, v = df.close.to_numpy(), df.high.to_numpy(), df.volume.to_numpy()
    e50, e200 = ema(c, 50), ema(c, 200)
    up = (c > e200) & (e50 > e200)
    if name == "trend_pullback":
        s = up & (rsi(c, 3) < p["th"])
    elif name == "range_breakout":
        hh = pd.Series(h).shift(1).rolling(p["n"]).max().to_numpy(); va = pd.Series(v).shift(1).rolling(24).mean().to_numpy()
        s = up & (c > hh) & (v > p["k"] * va)
    elif name == "vol_breakout":
        day = df.time.dt.floor("1D"); dopen = df.groupby(day).open.transform("first").to_numpy()
        a = atr(df); trig = dopen + p["k"] * a
        prev = np.roll(c, 1)
        s = (c > trig) & (prev <= np.roll(trig, 1)) & (c > e200)
    elif name == "dip_reversal":
        r24 = c / np.roll(c, 24) - 1
        s = (r24 <= -p["drop"]) & (rsi(c, 14) < 30)
    else:
        raise ValueError(name)
    if p.get("btc") and btc_up is not None:
        s = s & btc_up
    s[:210] = False
    return s


GRID = {
    "trend_pullback": [{"th": t, "btc": b} for t in (10, 20) for b in (False, True)],
    "range_breakout": [{"n": n, "k": k, "btc": b} for n in (24, 48) for k in (1.5, 2.5) for b in (False, True)],
    "vol_breakout": [{"k": k, "btc": b} for k in (0.5, 1.0) for b in (False, True)],
    "dip_reversal": [{"drop": d, "btc": False} for d in (0.06, 0.10)],
}
EXITS = [{"tp": tp, "sl": sl, "hold": hd} for (tp, sl) in ((0.015, 0.01), (0.03, 0.015), (0.05, 0.025)) for hd in (6, 24, 48)]


def main():
    with ThreadPoolExecutor(6) as ex:
        dfs = dict(zip(COINS, ex.map(load1h, COINS)))
    n = min(len(d) for d in dfs.values()); split = n - OOS_DAYS * 24
    dfs = {k: v.iloc[-n:].reset_index(drop=True) for k, v in dfs.items()}
    bc = dfs["BTC"].close.to_numpy(); btc_up = bc > ema(bc, 200)
    results = []
    for name, grid in GRID.items():
        for p, e in itertools.product(grid, EXITS):
            ins, oos, gross = [], [], []
            for sym, df in dfs.items():
                s = signals1h(df, name, p, btc_up)
                ins += run(df, s, e, 0, split); oos += run(df, s, e, split, n); gross += run(df, s, e, split, n, fee=0, slip=0)
            results.append({"strategy": name, "params": p, "exit": e, "in_sample": stats(ins), "oos": stats(oos), "oos_gross": stats(gross)})
    best = {}
    for r in results:
        if r["in_sample"]["trades"] < 40:
            continue
        b = best.get(r["strategy"])
        if b is None or r["in_sample"]["avg_pct"] > b["in_sample"]["avg_pct"]:
            best[r["strategy"]] = r
    winners = [b for b in best.values() if b["oos"]["trades"] >= 20 and (b["oos"]["avg_pct"] or -1) > 0]
    pick = max(winners, key=lambda b: b["oos"]["avg_pct"]) if winners else max(best.values(), key=lambda b: b["oos"]["avg_pct"] or -9)
    # ผลรายเดือนของตัวที่ดีที่สุด (ดูว่ากำไรมาจากช่วงไหน — ตลาดขึ้นหรือลง)
    btc_oos = round(float(bc[-1] / bc[split] - 1) * 100, 2); btc_is = round(float(bc[split] / bc[210] - 1) * 100, 2)
    out = {"generated_at": now_iso(), "interval": "1h", "coins": COINS, "days": DAYS, "oos_days": OOS_DAYS,
           "oos_from": str(dfs["BTC"].time.iloc[split]), "costs": {"round_trip_pct": round((FEE + SLIP) * 200, 2)},
           "btc_in_sample_pct": btc_is, "btc_oos_pct": btc_oos, "best_per_strategy": list(best.values()), "pick": pick,
           "passed": bool(winners)}
    (ROOT / "research" / "short_research.json").write_text(json.dumps(out | {"all": results}, indent=1, ensure_ascii=False, default=float))
    (ROOT / "docs" / "short_research.json").write_text(json.dumps(out, ensure_ascii=False, default=float))
    print(f"IS BTC {btc_is}% · OOS from {out['oos_from']} BTC {btc_oos}%")
    for b in best.values():
        print(f"{b['strategy']:15s} {b['params']} {b['exit']} | IS {b['in_sample']} | OOS {b['oos']} | gross {b['oos_gross']['avg_pct']}")
    print("PICK", pick["strategy"], pick["params"], pick["exit"], "PASSED" if winners else "none passed")
    # also show top OOS configs overall (for honesty about data-mining)
    top = sorted([r for r in results if r["oos"]["trades"] >= 20], key=lambda r: -(r["oos"]["avg_pct"] or -9))[:5]
    for r in top:
        print("  top-oos", r["strategy"], r["params"], r["exit"], r["oos"], "IS", r["in_sample"]["avg_pct"])


if __name__ == "__main__":
    main()
