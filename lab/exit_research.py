"""ทดสอบวิธี "ออก" ของ champion (keltner_trend) — หาวิธีที่ขาดทุนน้อยที่สุดแต่ยังเหลือกำไร.

ใช้ข้อมูลจริงช่วง out-of-sample เดียวกับ Judge (Top 20 ตามสภาพคล่องรายเดือน, 4h, ค่าธรรมเนียม 0.1% + slippage 0.05% ต่อข้าง)
พารามิเตอร์ของ champion คงที่ (k=2, stop=3×ATR) เปลี่ยนเฉพาะกฎการออก:
  base        : stop 3×ATR, trailing = ราคาปิดสูงสุด − 3×ATR, ขายเมื่อปิดต่ำกว่า EMA20  (กฎปัจจุบัน)
  be_1r       : + เมื่อกำไรถึง 1R เลื่อน stop มาที่ทุน (เทรดนั้นจะไม่ขาดทุนอีก)
  be_1.5r     : + เลื่อนมาที่ทุนเมื่อกำไร 1.5R
  stale_12    : + ถือ 12 แท่ง (2 วัน) แล้วยังไม่เคยขึ้นถึง +0.5R → ออก (ตัดเทรดที่ไม่ไปไหน)
  stop_2atr   : stop แคบลงเป็น 2×ATR
  be_1r+stale : รวม be_1r กับ stale_12
ผลนี้เป็น "ข้อเสนอ" — การเปลี่ยนกฎจริงใน config/strategy.yaml ต้องให้เจ้าของอนุมัติก่อน

python -m lab.exit_research
"""
from __future__ import annotations

import json
from dataclasses import replace

import numpy as np

from lab.data import ROOT, now_iso
from lab.engine import load_market, metrics, simulate
from lab.judge import FOLDS, idx
from lab.strategies import IDEAS

VARIANTS = {
    "base": {}, "be_1r": {"breakeven_r": 1.0}, "be_1.5r": {"breakeven_r": 1.5},
    "stale_12": {"stale_bars": 12}, "be_1r+stale": {"breakeven_r": 1.0, "stale_bars": 12},
}
TH = {"base": "กฎเดิม (ก่อน 25 พ.ย.)", "be_1r": "กำไรถึง 1R → เลื่อน stop มาที่ทุน (ใช้อยู่)", "be_1.5r": "กำไรถึง 1.5R → เลื่อน stop มาที่ทุน",
      "stale_12": "2 วันแล้วยังไม่ไปไหน → ออก", "be_1r+stale": "เลื่อนมาทุนที่ 1R + ตัดเทรดที่ไม่ไปไหน", "stop_2atr": "stop แคบลง (2×ATR)"}


def summarize(name, res) -> dict:
    mt, tr = metrics(res), res.trades
    win, loss = tr[tr.pnl > 0], tr[tr.pnl <= 0]
    return {"variant": name, "label": TH[name], "return_pct": round(mt["return"] * 100, 2), "sharpe": round(mt["sharpe"], 2),
            "max_dd_pct": round(mt["max_dd"] * 100, 2), "trades": int(len(tr)), "win_pct": round(len(win) / max(1, len(tr)) * 100, 1),
            "avg_win_r": round(float(win.r.mean()), 2) if len(win) else None, "avg_loss_r": round(float(loss.r.mean()), 2) if len(loss) else None,
            "expectancy_r": round(float(tr.r.mean()), 3) if len(tr) else None, "worst_r": round(float(tr.r.min()), 2) if len(tr) else None,
            "reasons": {k: int(v) for k, v in tr.reason.value_counts().items()}}


def mae_profile(m, res) -> dict:
    """ผู้ชนะเคยติดลบลึกแค่ไหนก่อนจะกำไร (หน่วย R) — ใช้ตัดสินว่า stop ควรห่างเท่าไหร่."""
    out = []
    sym_i = {s: j for j, s in enumerate(m.symbols)}
    for _, t in res.trades.iterrows():
        j, a, b = sym_i[t.symbol], m.times.get_loc(t.entry_time), m.times.get_loc(t.exit_time)
        lo = np.nanmin(m.low[a:b + 1, j])
        out.append({"win": t.pnl > 0, "mae_pct": (lo / t.entry - 1) * 100, "bars": int(t.bars)})
    w = [o["mae_pct"] for o in out if o["win"]]
    return {"winners": len(w), "winner_mae_median_pct": round(float(np.median(w)), 2) if w else None,
            "winner_mae_p90_pct": round(float(np.percentile(w, 10)), 2) if w else None,
            "median_bars_win": int(np.median([o["bars"] for o in out if o["win"]])) if w else None,
            "median_bars_loss": int(np.median([o["bars"] for o in out if not o["win"]])) if len(out) > len(w) else None}


def main():
    m = load_market()
    start = idx(m, FOLDS[0][1]); end = len(m.times)
    fn = IDEAS["keltner_trend"]["fn"]
    base_sig = fn(m, k=2.0, stop=3.0)
    rows, trades_base = [], None
    for name, kw in VARIANTS.items():
        res = simulate(m, replace(base_sig, **kw), start, end)
        rows.append(summarize(name, res))
        if name == "base": trades_base = res
    res2 = simulate(m, fn(m, k=2.0, stop=2.0), start, end); rows.append(summarize("stop_2atr", res2))
    base = rows[0]
    better = [r for r in rows[1:] if r["sharpe"] > base["sharpe"] and r["return_pct"] > 0 and (r["avg_loss_r"] or -9) >= (base["avg_loss_r"] or -9)]
    best = max(better, key=lambda r: r["sharpe"]) if better else None
    tr = trades_base.trades
    per_coin = {s: {"trades": int(len(g)), "win_pct": round(float((g.pnl > 0).mean() * 100), 1), "expectancy_r": round(float(g.r.mean()), 3)}
                for s, g in tr.groupby("symbol")}
    out = {"generated_at": now_iso(), "strategy": "keltner_trend", "params": {"k": 2.0, "stop": 3.0},
           "period": [str(m.times[start]), str(m.times[-1])], "variants": rows, "best": best["variant"] if best else None,
           "mae": mae_profile(m, trades_base), "per_coin": per_coin,
           "recent_trades": tr.tail(25).assign(entry_time=lambda d: d.entry_time.astype(str), exit_time=lambda d: d.exit_time.astype(str))
                              [["symbol", "entry_time", "exit_time", "entry", "exit", "r", "bars", "reason"]].round(4).to_dict("records")}
    (ROOT / "research" / "exit_research.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    for r in rows:
        print(f"{r['variant']:12s} ret {r['return_pct']:7.2f}% sharpe {r['sharpe']:5.2f} dd {r['max_dd_pct']:6.2f}% n {r['trades']:4d} win {r['win_pct']:5.1f}% "
              f"avgW {r['avg_win_r']} avgL {r['avg_loss_r']} E {r['expectancy_r']} {r['reasons']}")
    print("best:", out["best"], "| mae:", out["mae"])


if __name__ == "__main__":
    main()
