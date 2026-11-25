"""สมองตัดสินใจ: คิดทีละขั้นว่า "ควรซื้อเหรียญนี้ตอนนี้ไหม" และ "จะออกเมื่อไหร่" ตามกฎของ champion (keltner_trend).

ทุกขั้นใช้ตัวเลขจริงจากแท่ง 4h ที่ปิดแล้ว + สถิติจากการทดสอบย้อนหลังจริง (research/exit_research.json)
ผลลัพธ์อธิบายเป็นภาษาไทยให้อ่านเข้าใจได้ — ไม่ใช่การรับประกันกำไร
"""
from __future__ import annotations

import json

import numpy as np

from lab.data import ROOT
from lab.plans import px
from lab.strategies import atr, ema

EXIT_R = ROOT / "research" / "exit_research.json"


def _evidence() -> dict:
    if not EXIT_R.exists():
        return {}
    r = json.loads(EXIT_R.read_text())
    base = next((v for v in r["variants"] if v["variant"] == "be_1r"), None) or next((v for v in r["variants"] if v["variant"] == "base"), {})   # กฎที่ใช้อยู่ (อนุมัติ be_1r แล้ว)
    be = next((v for v in r["variants"] if v["variant"] == "be_1r"), {})
    return {"period": r["period"], "base": base, "be_1r": be, "best": r.get("best"), "mae": r.get("mae", {}), "per_coin": r.get("per_coin", {}),
            "recent": r.get("recent_trades", [])}


def think(m, rows: list[dict], cfg: dict, plans: list[dict], universe: list[str], positions: dict | None = None) -> list[dict]:
    champ = cfg["strategies"][0]; P = champ["params"]
    k, stop_mult = float(P.get("k", 2.0)), float(P.get("stop", 3.0))
    capital, risk = float(cfg["capital"]), float(cfg["risk_per_trade"])
    max_frac, fee = float(cfg["max_position_frac"]), 0.0015
    T = len(m.times) - 1
    c = m.df("close"); q = m.df("qvol")
    e20, e200, a20 = ema(c, 20), ema(c, 200), atr(m, 20)
    EV = _evidence(); base = EV.get("base", {}); mae = EV.get("mae", {})
    btc_c, btc_e = float(c["BTCUSDT"].iloc[T]), float(e200["BTCUSDT"].iloc[T])
    btc_up = btc_c > btc_e
    by = {r["symbol"]: r for r in rows}
    # ผู้สมัคร: ทุกแผน + เหรียญใน universe ที่คะแนนสูงสุด + สถานะที่ถืออยู่
    cands = [p["symbol"] for p in plans]
    liq = sorted([r for r in rows if r["status"] != "illiquid" and r.get("score") is not None], key=lambda r: -r["score"])
    cands += [r["symbol"] for r in liq if r["symbol"] + "USDT" in universe][:8] + [r["symbol"] for r in liq][:4]
    cands += list((positions or {}).keys())
    seen, out = set(), []
    for sym in cands:
        if sym in seen or sym == "BTC" and False:
            continue
        seen.add(sym)
        col = sym + "USDT"
        if col not in c.columns:
            continue
        close, prev = float(c[col].iloc[T]), float(c[col].iloc[T - 1])
        mid, slow, a = float(e20[col].iloc[T]), float(e200[col].iloc[T]), float(a20[col].iloc[T])
        if any(np.isnan(x) for x in (close, prev, mid, slow, a)) or a <= 0:
            continue
        trig = mid + k * a; trig_prev = float(e20[col].iloc[T - 1] + k * a20[col].iloc[T - 1])
        fresh = close > trig and prev <= trig_prev
        vol_x = float(q[col].iloc[T] / q[col].iloc[T - 20:T].mean()) if q[col].iloc[T - 20:T].mean() > 0 else None
        in_uni = col in universe
        pos = (positions or {}).get(sym)
        entry = pos["entry"] if pos else (close if fresh else trig)
        dist = stop_mult * a; stop = pos["stop"] if pos else entry - dist
        stop_pct = (entry - stop) / entry * 100
        size = min(capital * risk / (dist / entry), capital * max_frac)
        qty = size / entry; fee_usdt = size * fee * 2
        worst = qty * (entry - stop) + fee_usdt
        coin_ev = EV.get("per_coin", {}).get(col)
        steps = []

        def step(sid, q_, data, ok, why):
            steps.append({"id": sid, "q": q_, "data": data, "ok": ok, "why": why})

        step("market", "ตลาดรวมเป็นขาขึ้นไหม? (BTC เทียบเส้นเฉลี่ย 200 แท่ง)", f"BTC {btc_c:,.0f} vs EMA200 {btc_e:,.0f} ({(btc_c / btc_e - 1) * 100:+.1f}%)", btc_up,
             "กลยุทธ์นี้ผ่านการทดสอบเฉพาะตอน BTC อยู่เหนือ EMA200 — ตอนตลาดขาลง เหรียญส่วนใหญ่ร่วงตาม การซื้อจึงมีโอกาสโดน stop สูง" if not btc_up else "ตลาดรวมเป็นขาขึ้น เงินไหลเข้าคริปโต — เงื่อนไขพื้นฐานผ่าน")
        step("trend", f"{sym} อยู่ในขาขึ้นของตัวเองไหม?", f"ราคา {px(close)} vs EMA200 {px(slow)} ({(close / slow - 1) * 100:+.1f}%)", close > slow,
             "ราคาอยู่เหนือเส้นเฉลี่ยระยะยาว = แนวโน้มหลักเป็นขาขึ้น" if close > slow else "ราคายังอยู่ใต้เส้นเฉลี่ยระยะยาว = แนวโน้มหลักยังลง ซื้อแล้วต้องสู้กับกระแส")
        step("trigger", "มีแรงซื้อพิเศษเกิดขึ้นตอนนี้ไหม? (ปิดทะลุกรอบบน Keltner)", f"ราคาปิด {px(close)} vs กรอบบน {px(trig)} (EMA20 + {k}×ATR) → {'ทะลุแล้ว' if close > trig else f'ต้องขึ้นอีก {(trig / close - 1) * 100:.2f}%'}",
             fresh if not pos else True,
             "แท่ง 4h ล่าสุดเพิ่งปิดทะลุกรอบบน = แรงซื้อมากกว่าความผันผวนปกติ มักเป็นจุดเริ่มเทรนด์" if fresh else
             ("ปิดเหนือกรอบมาก่อนแล้ว — สัญญาณเกิดไปแล้ว ไม่ไล่ซื้อ รอรอบใหม่" if close > trig else "ยังไม่ทะลุ — รอให้แท่ง 4h ปิดเหนือกรอบบนก่อน ไม่ซื้อล่วงหน้า"))
        step("chase", "ราคาตอนนี้ยังไม่วิ่งหนีจุดสัญญาณไปไกลใช่ไหม?", f"ยอมให้ห่างจากกรอบบนได้ไม่เกิน 0.5×ATR = {px(trig + 0.5 * a)}", None,
             "ถ้าราคาวิ่งไปไกลแล้วค่อยซื้อ จุด stop จะไกลขึ้นและกำไรที่เหลือน้อยลง — หน้าเว็บตรวจข้อนี้ด้วยราคาสดทุกวินาที")
        step("volume", "มี volume ยืนยันไหม?", f"volume แท่งล่าสุด {vol_x:.2f} เท่าของค่าเฉลี่ย 20 แท่ง" if vol_x else "ไม่มีข้อมูล volume",
             None if vol_x is None else vol_x >= 1.0, "ข้อมูลประกอบ (ไม่ได้อยู่ในกฎที่ทดสอบ): volume สูงช่วยยืนยันว่าแรงซื้อจริง")
        step("tested", "เหรียญนี้อยู่ในกลุ่มที่ทดสอบย้อนหลังแล้วไหม?", "อยู่ใน Top 20 ตามสภาพคล่อง" if in_uni else "อยู่นอก Top 20", in_uni,
             "ผลทดสอบย้อนหลังครอบคลุมเหรียญกลุ่มนี้" if in_uni else "นอกกลุ่มที่ทดสอบ — สถิติด้านล่างอาจใช้กับเหรียญนี้ไม่ได้ ความเสี่ยงสูงกว่า")
        step("risk", "ถ้าผิด จะเสียเงินเท่าไหร่? คุมได้ไหม?", f"stop {px(stop)} (−{stop_pct:.1f}%) · ซื้อ {size:.2f} USDT · เสียสูงสุด ≈ {worst:.2f} USDT รวมค่าธรรมเนียม",
             worst <= capital * risk * 1.3,
             f"ตั้ง stop ห่าง {stop_mult}×ATR เพราะในอดีต เทรดที่สุดท้ายได้กำไร เคยติดลบระหว่างทางเฉลี่ย {mae.get('winner_mae_median_pct', '—')}% "
             f"(10% ลึกกว่า {mae.get('winner_mae_p90_pct', '—')}%) — stop แคบกว่านี้จะโดนสะบัดหลุดก่อนกำไร · ขนาดคำนวณให้เสียไม่เกิน {risk:.1%} ของทุน")
        exp_r = base.get("expectancy_r")
        step("edge", "ในอดีต กฎนี้ได้กำไรจริงไหมหลังหักค่าธรรมเนียม?",
             f"{base.get('trades', '—')} เทรด · ชนะ {base.get('win_pct', '—')}% · ชนะเฉลี่ย +{base.get('avg_win_r', '—')}R · แพ้เฉลี่ย {base.get('avg_loss_r', '—')}R · คาดหวัง {exp_r:+.3f}R/เทรด"
             if exp_r is not None else "ยังไม่มีผลทดสอบ", None if exp_r is None else exp_r > 0,
             "ชนะแค่ประมาณ 1 ใน 3 แต่ตอนชนะได้มากกว่าตอนแพ้ราว 2.5 เท่า (ตัดขาดทุนเร็ว ปล่อยกำไรวิ่ง) จึงยังเป็นบวกโดยรวม"
             + (f" · เฉพาะ {sym}: {coin_ev['trades']} เทรด ชนะ {coin_ev['win_pct']}% คาดหวัง {coin_ev['expectancy_r']:+.3f}R" if coin_ev else ""))
        hard = {s["id"]: s["ok"] for s in steps}
        if pos:
            verdict, head = "hold", "ถืออยู่ — ดูแผนออกด้านล่าง"
        elif hard["market"] and hard["trend"] and hard["trigger"] and hard["risk"] and (hard["edge"] is not False):
            verdict, head = "enter", "เข้าซื้อได้ (ต้องเช็คข้อ 'ไม่ไล่ราคา' ด้วยราคาสด)"
        elif hard["trend"]:
            NEED = {"market": "BTC ต้องกลับขึ้นเหนือ EMA200", "trigger": "ราคาต้องปิดทะลุกรอบบน Keltner (แท่ง 4h)", "risk": "ความเสี่ยงสูงเกินเพดาน"}
            miss = [NEED[s["id"]] for s in steps if s["ok"] is False and s["id"] in NEED]
            verdict, head = "wait", "รอก่อน — ยังขาด: " + ", ".join(miss)
        else:
            verdict, head = "no", "ไม่ซื้อ — เหรียญยังเป็นขาลง"
        R = entry - stop
        exits = [
            {"when": "ทันทีที่ซื้อ", "price": stop, "what": f"ตั้ง stop-loss ที่ {px(stop)} → ถ้าผิดทาง เสียไม่เกิน ≈ {worst:.2f} USDT", "kind": "stop"},
            {"when": f"ถ้ากำไรถึง +1R ({px(entry + R)})", "price": entry + R,
             "what": "เลื่อน stop มาที่ทุน + ค่าธรรมเนียม → จากจุดนี้เทรดนี้จะไม่ขาดทุนแล้ว", "kind": "breakeven",
             "status": "ใช้งานแล้ว — เจ้าของอนุมัติ 25 พ.ย. 2026"},
            {"when": "ระหว่างถือ", "price": None, "what": f"stop ขยับขึ้นตาม ราคาปิดสูงสุด − {stop_mult}×ATR ({px(dist)}) ไม่มีวันเลื่อนลง = ล็อกกำไรเมื่อราคาขึ้น", "kind": "trail"},
            {"when": "ทางออกหลัก", "price": mid, "what": f"แท่ง 4h ปิดต่ำกว่า EMA20 (ตอนนี้ ≈ {px(mid)}) → ขาย เพราะแรงซื้อหมดแล้ว", "kind": "ema"},
        ]
        bars_w, bars_l = mae.get("median_bars_win"), mae.get("median_bars_loss")
        out.append({
            "symbol": sym, "verdict": verdict, "headline": head, "in_universe": in_uni, "steps": steps,
            "plan": {"entry": entry, "stop": stop, "stop_pct": round(stop_pct, 2), "r": R, "size_usdt": round(size, 2), "qty": qty,
                     "fee_usdt": round(fee_usdt, 3), "worst_usdt": round(worst, 2), "one_r_price": entry + R, "two_r_price": entry + 2 * R,
                     "expected_usdt": round(exp_r * capital * risk, 3) if exp_r is not None else None,
                     "avg_win_usdt": round(base.get("avg_win_r", 0) * capital * risk, 2), "avg_loss_usdt": round(base.get("avg_loss_r", 0) * capital * risk, 2),
                     "typical_hold": f"ถ้าชนะ มักถือ ~{bars_w * 4 // 24 if bars_w else '—'} วัน · ถ้าแพ้ มักออกภายใน ~{round(bars_l * 4 / 24, 1) if bars_l else '—'} วัน"},
            "live": {"trigger": trig, "chase_max": trig + 0.5 * a, "ema20": mid, "ema200": slow, "atr": a, "close": close, "fresh": fresh},
            "exits": exits, "position": pos,
        })
    order = {"hold": 0, "enter": 1, "wait": 2, "no": 3}
    out.sort(key=lambda r: (order[r["verdict"]], not r["in_universe"]))
    return out[:20]


def evidence_summary() -> dict:
    e = _evidence()
    out = {k: e.get(k) for k in ("period", "base", "be_1r", "best", "mae")} | {"recent": e.get("recent", [])[-12:]}
    f = ROOT / "research" / "exit_research.json"
    if f.exists():
        out["exit_variants"] = json.loads(f.read_text())["variants"]
    g = ROOT / "research" / "regime_research.json"
    if g.exists():
        r = json.loads(g.read_text())
        out["regime"] = {k: r[k] for k in ("filters", "cross_stats", "period")}
        real = [x for x in r["crosses"] if x["stayed_above_days"] >= 3 and x["complete"]]
        out["regime"]["real_crosses"] = real[-8:]
    return out
