"""เรียนรู้การเทรดเร็ว (scalping) จากข้อมูลจริง: แท่ง 5 นาทีของ Binance spot ย้อนหลัง 180 วัน.

ทดสอบกลยุทธ์ "เข้าเร็ว-ออกเร็ว" แบบ long-only พร้อม take-profit / stop-loss / เวลาถือสูงสุด
- เข้าที่ราคาเปิดแท่งถัดไป (ไม่แอบดูอนาคต) + slippage
- ถ้าแท่งเดียวโดนทั้ง TP และ SL ถือว่าโดน SL ก่อน (ฝั่งระวัง)
- ค่าธรรมเนียม 0.1% + slippage 0.05% ต่อข้าง (ไปกลับ ≈ 0.30%) — รายงานผล "ก่อนค่าธรรมเนียม" คู่กันเพื่อให้เห็นว่าค่าธรรมเนียมกินไปเท่าไร
- เลือกพารามิเตอร์จาก 120 วันแรก (in-sample) แล้วตัดสินจาก 60 วันหลังที่ไม่เคยเห็น (out-of-sample)

python -m lab.scalp_research
"""
from __future__ import annotations

import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from lab.data import DATA, klines, now_iso

ROOT = Path(__file__).resolve().parent.parent
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "SUI", "LTC", "TRX"]
DAYS, OOS_DAYS = 180, 60
FEE, SLIP = 0.001, 0.0005
CACHE = DATA / "scalp"; CACHE.mkdir(parents=True, exist_ok=True)


def load(sym: str) -> pd.DataFrame:
    f = CACHE / f"{sym}USDT_5m.parquet"
    end = int(time.time() // 300 * 300 * 1000)
    if f.exists():
        df = pd.read_parquet(f); df["open_time"] = df["time"].dt.as_unit("ms").astype("int64")
        if (end - df["open_time"].iloc[-1]) < 6 * 3600 * 1000:
            return df
    df = klines(f"{sym}USDT", "5m", end - DAYS * 86400 * 1000, end)
    df["open_time"] = df["time"].dt.as_unit("ms").astype("int64")
    df.to_parquet(f)
    return df


def ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rsi(x, n):
    d = np.diff(x, prepend=x[0]); up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).to_numpy()


def signals(df: pd.DataFrame, name: str, p: dict) -> np.ndarray:
    c, h, v = df.close.to_numpy(), df.high.to_numpy(), df.volume.to_numpy()
    up = c > ema(c, 200)                     # เทรนด์ 5 นาทีเป็นขาขึ้น (~16 ชม.)
    if name == "momo_burst":                 # ทะลุจุดสูงสุด N แท่ง + volume พุ่ง
        hh = pd.Series(h).shift(1).rolling(p["n"]).max().to_numpy()
        va = pd.Series(v).shift(1).rolling(20).mean().to_numpy()
        return up & (c > hh) & (v > p["k"] * va)
    if name == "rsi2_dip":                   # ย่อแรงสั้นๆ ในขาขึ้น แล้วเด้ง
        return up & (rsi(c, 2) < p["th"])
    if name == "ema_cross":                  # EMA9 ตัดขึ้น EMA21
        f, s = ema(c, 9), ema(c, 21)
        return up & (f > s) & (np.roll(f, 1) <= np.roll(s, 1))
    if name == "bb_bounce":                  # หลุดขอบล่าง Bollinger ในขาขึ้น
        m = pd.Series(c).rolling(20).mean(); sd = pd.Series(c).rolling(20).std()
        return up & (c < (m - p["k"] * sd).to_numpy())
    raise ValueError(name)


GRID = {
    "momo_burst": [{"n": n, "k": k} for n in (12, 36) for k in (2.0, 3.0)],
    "rsi2_dip": [{"th": t} for t in (5, 10)],
    "ema_cross": [{}],
    "bb_bounce": [{"k": k} for k in (2.0, 2.5)],
}
EXITS = [{"tp": tp, "sl": sl, "hold": hd} for (tp, sl) in ((0.006, 0.004), (0.01, 0.006), (0.015, 0.01), (0.025, 0.012)) for hd in (12, 48)]


def run(df: pd.DataFrame, sig: np.ndarray, ex: dict, lo: int, hi: int, fee=FEE, slip=SLIP) -> list[float]:
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    out, i = [], max(lo, 200)
    idx = np.flatnonzero(sig[:hi - 1]); idx = idx[idx >= i]
    k = 0
    while k < len(idx):
        s = idx[k]
        if s < i: k += 1; continue
        e = s + 1; px = o[e] * (1 + slip); tp, sl = px * (1 + ex["tp"]), px * (1 - ex["sl"])
        end = min(e + ex["hold"], hi - 1); exit_px, j = c[end], end
        for j in range(e, end + 1):
            if l[j] <= sl: exit_px = sl; break
            if h[j] >= tp: exit_px = tp; break
        else:
            j = end
        exit_px *= (1 - slip)
        out.append((exit_px * (1 - fee)) / (px * (1 + fee)) - 1)
        i = j + 1; k += 1
    return out


def stats(r: list[float]) -> dict:
    if not r:
        return {"trades": 0, "win_pct": None, "avg_pct": None, "total_pct": 0.0}
    a = np.array(r)
    return {"trades": len(a), "win_pct": round(float((a > 0).mean() * 100), 1), "avg_pct": round(float(a.mean() * 100), 3),
            "total_pct": round(float((np.prod(1 + a) - 1) * 100), 2)}


def main():
    with ThreadPoolExecutor(6) as ex:
        dfs = dict(zip(COINS, ex.map(load, COINS)))
    n = min(len(d) for d in dfs.values()); split = n - OOS_DAYS * 288
    results = []
    for name, grid in GRID.items():
        for p, e in itertools.product(grid, EXITS):
            ins, oos, oos_gross = [], [], []
            for sym, df in dfs.items():
                df = df.iloc[-n:].reset_index(drop=True); s = signals(df, name, p)
                ins += run(df, s, e, 0, split); oos += run(df, s, e, split, n)
                oos_gross += run(df, s, e, split, n, fee=0, slip=0)
            results.append({"strategy": name, "params": p, "exit": e, "in_sample": stats(ins), "oos": stats(oos), "oos_gross": stats(oos_gross)})
    # เลือกตัวที่ดีที่สุดของแต่ละกลยุทธ์จาก in-sample (ต้องมีเทรด ≥ 30 ครั้ง) แล้วดูผล OOS
    best = {}
    for r in results:
        if r["in_sample"]["trades"] < 30: continue
        b = best.get(r["strategy"])
        if b is None or (r["in_sample"]["avg_pct"] or -9) > (b["in_sample"]["avg_pct"] or -9): best[r["strategy"]] = r
    btc = dfs["BTC"].iloc[-n:].reset_index(drop=True)
    bench = round((btc.close.iloc[-1] / btc.open.iloc[split] - 1) * 100, 2)
    winners = [b for b in best.values() if b["oos"]["trades"] >= 20 and (b["oos"]["avg_pct"] or -1) > 0]
    pick = max(winners, key=lambda b: b["oos"]["avg_pct"]) if winners else max(best.values(), key=lambda b: b["oos"]["avg_pct"] or -9)
    out = {"generated_at": now_iso(), "coins": COINS, "interval": "5m", "days": DAYS, "oos_days": OOS_DAYS,
           "oos_from": str(pd.to_datetime(btc.open_time.iloc[split], unit="ms", utc=True)),
           "costs": {"fee_per_side": FEE, "slippage_per_side": SLIP, "round_trip_pct": round((FEE + SLIP) * 2 * 100, 2)},
           "btc_buy_hold_oos_pct": bench, "best_per_strategy": list(best.values()), "pick": pick,
           "passed": bool(winners), "all": results}
    (ROOT / "research" / "scalp_research.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    (ROOT / "docs" / "scalp_research.json").write_text(json.dumps({k: v for k, v in out.items() if k != "all"}, ensure_ascii=False))
    print(f"OOS from {out['oos_from']} · BTC buy&hold {bench}%")
    for b in best.values():
        print(f"{b['strategy']:11s} {b['params']} {b['exit']} | IS {b['in_sample']} | OOS {b['oos']} | gross {b['oos_gross']['avg_pct']}")
    print("PICK", pick["strategy"], pick["params"], pick["exit"], "passed" if winners else "NO STRATEGY PASSED")


if __name__ == "__main__":
    main()
