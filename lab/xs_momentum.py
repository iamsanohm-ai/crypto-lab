"""Cross-sectional momentum แบบไม่เสี่ยงทิศทางตลาด: long เหรียญที่แข็งที่สุด + short เหรียญที่อ่อนที่สุด ใน Top 20 (perpetual ทั้งสองขา).

อ้างอิง: Liu, Tsyvinski & Wu (2022) "Common Risk Factors in Cryptocurrency" — momentum เป็นปัจจัยที่อธิบายผลตอบแทนคริปโต
คำนวณแบบตรง (ไม่ใช้วิธีกลับราคา):
  ทุก H วัน: จัดอันดับ Top 20 (point-in-time) ตามผลตอบแทน L วันที่ผ่านมา → long N ตัวบน, short N ตัวล่าง น้ำหนักเท่ากัน (ครึ่งทุนต่อฝั่ง)
  ผลตอบแทนช่วง = เฉลี่ย(long) − เฉลี่ย(short) − ค่าธรรมเนียมตามสัดส่วนที่เปลี่ยน (0.05% fee + 0.05% slippage ต่อข้าง) + funding จริง
เลือกพารามิเตอร์จากช่วง in-sample (2022-11 → 2023-11) แล้ววัดผลจริงช่วง out-of-sample (2023-11 → ปัจจุบัน) และแยกผลตอนตลาดขาลง

python -m lab.xs_momentum
"""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from lab.data import ROOT, now_iso
from lab.engine import load_market
from lab.judge import FOLDS, idx
from lab.strategies import ema

COST = 0.0005 + 0.0005


def run(m, L, H, N, start, end, mode="ls"):
    c = m.df("close"); fund = pd.DataFrame(np.nan_to_num(m.funding), index=m.times, columns=m.symbols)
    btc = c["BTCUSDT"]; up = (btc > ema(btc.to_frame(), 200)["BTCUSDT"])
    step, lb = H * 6, L * 6                      # แท่ง 4 ชม. ต่อวัน = 6
    rets, dates, wprev, regime = [], [], {}, []
    for t in range(max(start, lb + 1), end - step - 1, step):
        # ไม่ใช้ข้อมูลอนาคต: เลือกจากสมาชิก Top 20 ณ เวลานั้นเท่านั้น (เหรียญที่จะถูกถอดภายหลังยังอยู่ในการคำนวณ)
        mem = [j for j in range(len(m.symbols)) if m.member[t, j] and not np.isnan(c.iat[t, j]) and not np.isnan(c.iat[t - lb, j]) and t + 1 <= m.last_bar[j]]
        if len(mem) < 2 * N + 2: continue
        mom = sorted(mem, key=lambda j: c.iat[t, j] / c.iat[t - lb, j])
        longs, shorts = mom[-N:], mom[:N]
        if mode == "short_weak_hedged":           # short เหรียญอ่อน + long BTC เท่ากัน (hedge ทิศทาง)
            b = m.symbols.index("BTCUSDT"); longs = [b]
        w = {}
        for j in longs: w[j] = w.get(j, 0) + 0.5 / len(longs)
        for j in shorts: w[j] = w.get(j, 0) - 0.5 / len(shorts)
        r = 0.0
        for j, wj in w.items():
            p0 = m.open[t + 1, j]                    # เข้าที่ราคาเปิดแท่งถัดไป
            if np.isnan(p0): p0 = c.iat[t, j]
            if t + step > m.last_bar[j]:               # ถูกถอดระหว่างถือ: ปิดที่ราคาสุดท้าย หักเพิ่ม 2% (เหมือน engine)
                p1 = c.iat[m.last_bar[j], j] * (1 - 0.02 * np.sign(wj))
            else:
                p1 = m.open[t + step + 1, j] if t + step + 1 < len(m.times) and not np.isnan(m.open[t + step + 1, j]) else c.iat[t + step, j]
            r += wj * (p1 / p0 - 1) * 2               # ทุนแต่ละฝั่ง = ครึ่งหนึ่ง → ผลตอบแทนต่อทุนรวม
            r -= wj * fund.iloc[t:t + step, j].sum() * 2 / 2   # long จ่าย funding, short ได้รับ (ประมาณครึ่งรอบต่อแท่ง)
        turnover = sum(abs(w.get(j, 0) - wprev.get(j, 0)) for j in set(w) | set(wprev))
        r -= turnover * COST * 2
        wprev = w; rets.append(r / 2); dates.append(m.times[t + step]); regime.append(bool(up.iat[t]))
    s = pd.Series(rets, index=dates)
    return s, pd.Series(regime, index=dates)


def summarize(s, reg, H):
    if not len(s): return None
    e = (1 + s).cumprod(); per_year = 365 / H
    def part(mask):
        x = s[mask]
        return None if not len(x) else {"periods": int(len(x)), "total_pct": round(float(((1 + x).prod() - 1) * 100), 1), "avg_pct": round(float(x.mean() * 100), 2), "win_pct": round(float((x > 0).mean() * 100), 1)}
    return {"total_pct": round(float((e.iloc[-1] - 1) * 100), 1), "sharpe": round(float(s.mean() / s.std() * np.sqrt(per_year)), 2) if s.std() > 0 else 0,
            "max_dd_pct": round(float((e / e.cummax() - 1).min() * 100), 1), "periods": int(len(s)),
            "btc_down": part(~reg), "btc_up": part(reg),
            "by_year": {str(y): round(float(((1 + g).prod() - 1) * 100), 1) for y, g in s.groupby(s.index.year)}}


def ensemble(m, lo, hi) -> dict:
    """แบ่งทุนเท่ากันให้ทั้ง 12 ชุด (ไม่เลือกตัวที่ดีที่สุด เพื่อไม่หลอกตัวเอง)."""
    btc = m.df("close")["BTCUSDT"]; up = btc > ema(btc.to_frame(), 200)["BTCUSDT"]
    days = pd.date_range(m.times[lo], m.times[hi - 1], freq="1D", tz="UTC"); curves = []
    for L, H, N in itertools.product((7, 14, 30), (7, 14), (3, 5)):
        s, _ = run(m, L, H, N, lo, hi); curves.append((1 + s).cumprod().reindex(days, method="ffill").fillna(1.0))
    e = pd.concat(curves, axis=1).mean(axis=1); d = e.pct_change().dropna(); u = up.reindex(d.index, method="ffill").fillna(False).astype(bool)
    return {"total_pct": round(float((e.iloc[-1] - 1) * 100), 1), "sharpe": round(float(d.mean() / d.std() * np.sqrt(365)), 2),
            "max_dd_pct": round(float((e / e.cummax() - 1).min() * 100), 1), "btc_down_pct": round(float(((1 + d[~u]).prod() - 1) * 100), 1),
            "btc_up_pct": round(float(((1 + d[u]).prod() - 1) * 100), 1),
            "by_year": {str(y): round(float(((1 + x).prod() - 1) * 100), 1) for y, x in d.groupby(d.index.year)},
            "curve": [[str(t.date()), round(float(v), 4)] for t, v in e.iloc[::3].items()]}


def main():
    m = load_market(); s0 = idx(m, FOLDS[0][0]); split = idx(m, FOLDS[0][1]); end = len(m.times)
    grid = list(itertools.product((7, 14, 30), (7, 14), (3, 5)))
    rows = []
    for L, H, N in grid:
        a, ra = run(m, L, H, N, s0, split); b, rb = run(m, L, H, N, split, end)
        rows.append({"L": L, "H": H, "N": N, "in_sample": summarize(a, ra, H), "oos": summarize(b, rb, H)})
    ok = [r for r in rows if r["in_sample"]]
    best = max(ok, key=lambda r: r["in_sample"]["sharpe"])
    hedged_b, hr = run(m, best["L"], best["H"], best["N"], split, end, mode="short_weak_hedged")
    out = {"generated_at": now_iso(), "in_sample": [str(m.times[s0]), str(m.times[split])], "oos": [str(m.times[split]), str(m.times[-1])],
           "costs": {"per_side": COST, "funding": "จริง (data.binance.vision)"}, "grid": rows, "pick_by_in_sample": best,
           "short_weak_hedged_oos": summarize(hedged_b, hr, best["H"])}
    out["ensemble_oos"] = ensemble(m, split, end); out["ensemble_in_sample"] = ensemble(m, s0, split)
    b_ = m.df("close")["BTCUSDT"].iloc[split:]; out["btc_buy_hold_oos"] = {"total_pct": round(float(b_.iloc[-1] / b_.iloc[0] - 1) * 100, 1), "max_dd_pct": round(float((b_ / b_.cummax() - 1).min() * 100), 1)}
    (ROOT / "docs" / "xs_research.json").write_text(json.dumps({k: out[k] for k in ("generated_at", "in_sample", "oos", "ensemble_oos", "ensemble_in_sample", "btc_buy_hold_oos")}, ensure_ascii=False, default=float))
    (ROOT / "research" / "xs_momentum.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    for r in rows:
        i, o = r["in_sample"], r["oos"]
        print(f"L{r['L']:>2} H{r['H']:>2} N{r['N']} | IS {i['total_pct']:+6.1f}% S{i['sharpe']:+.2f} | OOS {o['total_pct']:+6.1f}% S{o['sharpe']:+.2f} DD{o['max_dd_pct']:6.1f}% "
              f"| BTC-down {o['btc_down']['total_pct'] if o['btc_down'] else '—'}% ({o['btc_down']['periods'] if o['btc_down'] else 0}) years {o['by_year']}")
    print("PICK (by IS Sharpe):", {k: best[k] for k in "LHN"}, "OOS", best["oos"]["total_pct"], "%")
    print("ENSEMBLE OOS:", {k: v for k, v in out["ensemble_oos"].items() if k != "curve"})


if __name__ == "__main__":
    main()
