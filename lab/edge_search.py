"""ค้นหากลยุทธ์ที่ทำกำไรได้ในตลาดขาลงด้วย — ทดสอบกับข้อมูลจริง (Top 20 รายเดือน, แท่ง 4h, funding จริง) ช่วง OOS เดียวกับ Judge.

1) short_trend  : (ผล: ขาดทุนเมื่อคำนวณแบบ short จริง) กระจกเงาของ champion — short futures เมื่อปิดหลุดกรอบล่าง Keltner (EMA20 − k×ATR) ใต้ EMA200 และ BTC ขาลง,
                  ปิดเมื่อปิดเหนือ EMA20, stop 3×ATR + trailing, ค่าธรรมเนียม futures 0.05% + slippage 0.05% ต่อข้าง, funding จริง (short ได้รับเมื่อเป็นบวก)
2) both_ways    : champion (long spot ตอน BTC ขาขึ้น) + short_trend (ตอน BTC ขาลง) ในบัญชีเดียว
3) funding_carry: ซื้อ spot + short perpetual เท่ากัน (ไม่เสี่ยงทิศทางราคา) ถือเฉพาะเหรียญ/ช่วงที่ funding 3 วันล่าสุดเป็นบวก — รายได้ = funding − ค่าธรรมเนียมเปิด/ปิด
ไม่มีการปรับพารามิเตอร์ให้เข้ากับข้อมูล (ใช้ค่าเดียวกับ champion) — ผลจึงเป็น out-of-sample ทั้งหมด

python -m lab.edge_search
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lab.data import ROOT, now_iso
from lab.engine import load_market
from lab.judge import FOLDS, idx
from lab.strategies import atr, ema

FUT_FEE, SLIP, SPOT_FEE = 0.0005, 0.0005, 0.001


def exact_short(m, start, end, k=2.0, btc_filter=True):
    """short ด้วย engine เดิม (กลับราคาเป็น 1/ราคา) แล้วคำนวณกำไรขาดทุนรายเทรดใหม่แบบ short จริง — วิธีกลับราคาให้ผลดีเกินจริง."""
    from dataclasses import replace as _r
    from lab.engine import Costs, Signals, simulate
    c = m.df("close"); a = atr(m, 20); mid = ema(c, 20); e200 = ema(c, 200)
    btc = c["BTCUSDT"]; up = (btc > ema(btc.to_frame(), 200)["BTCUSDT"]).to_numpy()[:, None]
    inv = _r(m, open=1 / m.open, high=1 / m.low, low=1 / m.high, close=1 / m.close)
    e = ((c < mid - k * a) & (c.shift(1) >= mid.shift(1) - k * a.shift(1)) & (c < e200)).fillna(False).to_numpy()
    if btc_filter: e = e & ~up
    cc, aa = c.to_numpy(), a.to_numpy()
    sig = Signals(e, 1 / cc - 1 / (cc + 3 * aa), exit=(c > mid).fillna(False).to_numpy(), trail_atr=1 / cc - 1 / (cc + 3 * aa), breakeven_r=1.0)
    fut = Costs(fee=FUT_FEE, slippage=SLIP); tr = simulate(inv, sig, start, end, costs=fut).trades
    N = tr.cost / (1 + fut.per_side); exact = N * (1 - tr.entry / tr.exit) - N * fut.per_side * (1 + tr.entry / tr.exit)
    fund = np.nan_to_num(m.funding)
    fsum = sum(t.cost * np.nansum(fund[m.times.get_loc(t.entry_time):m.times.get_loc(t.exit_time), m.symbols.index(t.symbol)]) / 2 for _, t in tr.iterrows())
    return {"trades": int(len(tr)), "inverse_method_pnl_usdt": round(float(tr.pnl.sum()), 1), "exact_pnl_usdt": round(float(exact.sum() + fsum), 1),
            "win_pct": round(float((exact > 0).mean() * 100), 1), "by_exit_year_usdt": {str(k_): round(float(v), 1) for k_, v in tr.assign(y=pd.to_datetime(tr.exit_time).dt.year, ex=exact).groupby("y").ex.sum().items()}}


def carry(m, start, end, enter=0.0001, exitv=0.0, lb=18, maxc=5, fee_rt=2 * (0.00075 + 0.0002)):
    """เก็บ funding: ซื้อ spot + short perp เท่ากัน ถือเมื่อ funding เฉลี่ย (lb แท่ง) > enter, ปิดเมื่อ < exitv. ทุน 500 แบ่ง 5 ช่อง (notional ต่อขา)."""
    fund = pd.DataFrame(m.funding, index=m.times, columns=m.symbols); avg = fund.rolling(lb).mean()
    held, cash, eq, n, alloc = set(), 500.0, [], 0, 500 / maxc
    for t in range(start, end):
        row = avg.iloc[t]
        for s in list(held):
            j = m.symbols.index(s)
            if not (row[s] > exitv) or not m.member[t, j] or t > m.last_bar[j]: cash -= alloc * fee_rt / 2; held.discard(s)
        for j in np.argsort(-np.nan_to_num(row.to_numpy(), nan=-9)):
            if len(held) >= maxc: break
            s = m.symbols[j]
            if s in held or not m.member[t, j] or not row[s] > enter: continue
            held.add(s); cash -= alloc * fee_rt / 2; n += 1
        for s in held:
            f = fund.iloc[t][s]
            if not np.isnan(f): cash += alloc * f / 2
        eq.append(cash)
    e = pd.Series(eq, index=m.times[start:end])
    return {"return_pct": round(float(e.iloc[-1] / 500 - 1) * 100, 2), "max_dd_pct": round(float((e / e.cummax() - 1).min() * 100), 2), "positions_opened": n,
            "by_year": {str(y): round(float(g.iloc[-1] / g.iloc[0] - 1) * 100, 1) for y, g in e.groupby(e.index.year)},
            "params": {"enter": enter, "exit": exitv, "lookback_bars": lb, "max_coins": maxc, "fee_round_trip_both_legs": fee_rt}}


def main():
    m = load_market(); start = idx(m, FOLDS[0][1]); end = len(m.times)
    out = {"generated_at": now_iso(), "period": [str(m.times[start]), str(m.times[-1])],
           "short_trend": {"btc_down_only": exact_short(m, start, end), "always": exact_short(m, start, end, btc_filter=False)},
           "funding_carry": {"maker_bnb": carry(m, start, end), "market": carry(m, start, end, fee_rt=2 * (SPOT_FEE + FUT_FEE + 2 * SLIP))},
           "notes": ["short_trend: กำไรจากวิธีกลับราคา (inverse) เป็นผลหลอก — ผลจริงขาดทุน ไม่ใช้",
                     "funding_carry (limit order + BNB): บวกทุกปี ขาดทุนสะสมสูงสุดต่ำมาก แต่ยังไม่รวมความเสี่ยง basis/การถูกบังคับปิดขา short และต้องใช้ทุนสำหรับ margin ขา futures เพิ่ม",
                     "ต้องใช้บัญชี Binance Futures — เซิร์ฟเวอร์ GitHub (สหรัฐฯ) ถูก Binance บล็อก จึงส่งออเดอร์ได้จากเครื่องเจ้าของเท่านั้น"]}
    (ROOT / "research" / "edge_search.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float))
    (ROOT / "docs" / "edge_search.json").write_text(json.dumps(out, ensure_ascii=False, default=float))
    print(json.dumps(out, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
