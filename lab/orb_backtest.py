"""ทดสอบว่าคะแนน ORB มีประโยชน์จริงไหม: คำนวณคะแนนย้อนหลังทุกสัปดาห์ (ใช้ข้อมูล ณ เวลานั้นเท่านั้น)
แล้ววัดผลตอบแทนจริง 7 และ 30 วันถัดไป (เข้าที่ราคาเปิดแท่งถัดไป หักค่าธรรมเนียม+slippage ไป-กลับ 0.3%)

ผลลัพธ์: research/orb_validation.json (dashboard อ่านไปแสดง)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lab import orb
from lab.data import ROOT, now_iso
from lab.engine import load_market
from lab.judge import FOLDS, idx
from lab.strategies import atr, ema

COST = 0.003
HORIZONS = {"7d": 42, "30d": 180}
BUCKETS = [(0, 40, "0–39"), (40, 60, "40–59"), (60, 80, "60–79"), (80, 101, "80–100")]


def compute_scores(m):
    """คะแนน ORB ทุกแท่งทุกเหรียญ (vectorized) — คืน DataFrame ยาว: time, symbol, score, raw, capped."""
    c = m.df("close")
    e200 = ema(c, 200)
    vs = (c / e200 - 1) * 100
    mom = c.pct_change(180, fill_method=None) * 100
    qv24 = m.df("qvol").rolling(6, min_periods=6).sum()
    liq = np.log10(qv24.where(qv24 > 0))
    a14, a20 = atr(m, 14), atr(m, 20)
    atrp = a14 / c * 100
    entry = ((ema(c, 20) + 2 * a20) / c - 1) * 100

    def comp(name, x):
        w, g, b, _ = orb.COMPONENTS[name]
        return (10 * w * ((b - x) / (b - g)).clip(0, 1)).round() / 10

    raw = (comp("trend", vs).fillna(0) + comp("momentum", mom).fillna(0) + comp("liquidity", liq).fillna(0)
           + comp("volatility", atrp).fillna(0) + comp("entry", entry).fillna(0)).round()
    btc_up = (c["BTCUSDT"] > e200["BTCUSDT"])
    capped = (qv24 < 2e6) | (c < e200) | e200.isna()
    capped = capped.apply(lambda col: col | ~btc_up)
    final = raw.where(~capped, np.minimum(raw, 59))
    return raw, final, capped


def main():
    m = load_market(top_n=100)
    raw, final, capped = compute_scores(m)
    c, o = m.df("close"), m.df("open")
    member = m.df("member").astype(bool)
    start = idx(m, FOLDS[0][1])
    sample = list(range(start, len(m.times) - 1, 42))   # ทุก 7 วัน
    rows = []
    for t in sample:
        mem = member.iloc[t]
        for sym in m.symbols:
            if not mem[sym] or np.isnan(c.iloc[t][sym]):
                continue
            rec = {"t": t, "time": m.times[t], "symbol": sym, "score": float(final.iloc[t][sym]),
                   "raw": float(raw.iloc[t][sym]), "capped": bool(capped.iloc[t][sym])}
            for h, n in HORIZONS.items():
                if t + n < len(m.times) and not np.isnan(o.iloc[t + 1][sym]):
                    last = c[sym].iloc[t + 1:t + n + 1].dropna()
                    exit_px = last.iloc[-1] if len(last) else np.nan
                    # เหรียญที่ถูกถอดระหว่างทาง → ใช้ราคาสุดท้าย หัก 2%
                    if len(last) and last.index[-1] < m.times[t + n]:
                        exit_px *= 0.98
                    rec[h] = float(exit_px / o.iloc[t + 1][sym] - 1 - COST)
            rows.append(rec)
    df = pd.DataFrame(rows)
    out = {"generated_at": now_iso(), "period": [str(m.times[start].date()), str(m.times[-1].date())],
           "universe": "Top 100 ตามสภาพคล่องรายเดือน (point-in-time รวมเหรียญที่ถูกถอด)", "samples": int(len(df)),
           "weeks": len(sample), "cost_roundtrip": COST, "horizons": {}}
    for h in HORIZONS:
        d = df.dropna(subset=[h])
        buckets = []
        for lo, hi, label in BUCKETS:
            g = d[(d.score >= lo) & (d.score < hi)]
            buckets.append({"bucket": label, "n": int(len(g)), "mean_pct": round(float(g[h].mean() * 100), 2) if len(g) else None,
                            "median_pct": round(float(g[h].median() * 100), 2) if len(g) else None,
                            "win_rate_pct": round(float((g[h] > 0).mean() * 100), 1) if len(g) else None})
        # Information Coefficient: rank correlation ระหว่างคะแนนดิบกับผลตอบแทนถัดไป ต่อสัปดาห์
        ics = [g["raw"].rank().corr(g[h].rank()) for _, g in d.groupby("t") if len(g) >= 10]
        ics = [x for x in ics if not np.isnan(x)]
        top = d[d.score >= 60]
        allc = d
        uncapped_hi = d[(~d.capped) & (d.raw >= 70)]
        out["horizons"][h] = {
            "buckets": buckets,
            "ic_mean": round(float(np.mean(ics)), 3) if ics else None,
            "ic_positive_weeks_pct": round(float(np.mean([x > 0 for x in ics]) * 100), 1) if ics else None,
            "all_mean_pct": round(float(allc[h].mean() * 100), 2),
            "top_minus_all_pct": round(float((top[h].mean() - allc[h].mean()) * 100), 2) if len(top) else None,
            "uncapped_70_mean_pct": round(float(uncapped_hi[h].mean() * 100), 2) if len(uncapped_hi) else None,
            "uncapped_70_n": int(len(uncapped_hi)),
            "capped_mean_pct": round(float(d[d.capped][h].mean() * 100), 2),
            "capped_n": int(d.capped.sum()),
        }
    h = out["horizons"]["30d"]
    b = {x["bucket"]: x["mean_pct"] for x in h["buckets"] if x["mean_pct"] is not None}
    best = max(b, key=b.get)
    low_worst = b.get("0–39", 0) == min(b.values())
    top_best = best == "80–100"
    ic_ok = (h["ic_mean"] or 0) > 0.02
    out["best_bucket"] = best
    if ic_ok and top_best:
        out["verdict"], out["verdict_th"] = "useful", "คะแนนยิ่งสูง ผลตอบแทน 30 วันถัดไปยิ่งดีในอดีต — ใช้จัดลำดับได้"
    elif ic_ok and low_worst:
        out["verdict"] = "filter"
        out["verdict_th"] = (f"ใช้ได้เป็น 'ตัวกรอง' — เหรียญคะแนน 0–39 ผลตอบแทนแย่ที่สุด ({b['0–39']:+.1f}% ใน 30 วัน) ควรเลี่ยง "
                             f"แต่คะแนนสูงสุดไม่ได้ดีที่สุด (ช่วงที่ดีที่สุดคือ {best}) เพราะมักเป็นเหรียญที่วิ่งไปไกลแล้ว — อย่าไล่ซื้อเพราะคะแนนสูงอย่างเดียว")
    else:
        out["verdict"], out["verdict_th"] = "weak", "คะแนนแยกเหรียญดี/ไม่ดีได้ไม่ชัดเจนในอดีต — ใช้ดูภาพรวมเท่านั้น"
    (ROOT / "research" / "orb_validation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("samples", "weeks", "verdict", "best_bucket", "verdict_th")}, ensure_ascii=False))
    for hk, hv in out["horizons"].items():
        print(hk, "IC", hv["ic_mean"], "IC+ weeks", hv["ic_positive_weeks_pct"], "| all", hv["all_mean_pct"], "| top-all", hv["top_minus_all_pct"],
              "| uncapped≥70", hv["uncapped_70_mean_pct"], f"(n={hv['uncapped_70_n']})", "| capped", hv["capped_mean_pct"])
        for b in hv["buckets"]:
            print("   ", b)


if __name__ == "__main__":
    main()
