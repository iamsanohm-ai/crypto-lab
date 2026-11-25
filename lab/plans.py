"""แผนเทรด: บอกว่า "เข้าที่ราคาไหน, stop ที่ไหน, ออกเมื่อไหร่, ซื้อเท่าไหร่" ตามกฎของ champion (keltner_trend)
ที่ผ่าน walk-forward backtest — ไม่ใช่การเดา และไม่รับประกันกำไร

ใช้กับทุกเหรียญที่มีสภาพคล่องบนกระดาน แต่ติดป้ายชัดเจนว่าเหรียญนอก Top 20 "ยังไม่ผ่าน backtest"
"""
from __future__ import annotations

import json

import numpy as np

from lab.data import ROOT
from lab.strategies import atr, ema

ALERTS = ROOT / "state" / "plan_alerts.json"


def px(x: float) -> str:
    """ราคาแบบอ่านง่าย ไม่มี e-05."""
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.4f}"
    d = max(4, -int(np.floor(np.log10(abs(x)))) + 3) if x else 4
    return f"{x:.{d}f}"


def build(m, rows: list[dict], cfg: dict, btc_up: bool, universe: list[str]) -> list[dict]:
    champ = cfg["strategies"][0]
    k = float(champ["params"].get("k", 2.0))
    stop_mult = float(champ["params"].get("stop", 3.0))
    capital, risk = float(cfg["capital"]), float(cfg["risk_per_trade"])
    max_frac = float(cfg["max_position_frac"])
    T = len(m.times) - 1
    c = m.df("close")
    e20, e200 = ema(c, 20), ema(c, 200)
    a20 = atr(m, 20)
    by_sym = {r["symbol"] + "USDT": r for r in rows}
    plans = []
    for j, sym in enumerate(m.symbols):
        r = by_sym.get(sym)
        if r is None or r["status"] == "illiquid":
            continue
        close, ema20_, ema200_, a = float(c.iloc[T, j]), float(e20.iloc[T, j]), float(e200.iloc[T, j]), float(a20.iloc[T, j])
        if any(np.isnan(x) for x in (close, ema20_, ema200_, a)) or a <= 0:
            continue
        trigger = ema20_ + k * a
        in_uni = sym in universe
        fired = "keltner_trend" in [n for n in (r.get("buy_signals") or "").split(", ")] or r["status"] == "buy_signal"
        above = close > ema200_
        dist = (trigger / close - 1) * 100
        if fired and above:
            state = "enter_now" if btc_up else "wait_btc"
            entry = close
        elif above and 0 < dist <= 6:
            state = "near" if btc_up else "wait_btc"
            entry = trigger
        else:
            continue
        stop = entry - stop_mult * a
        stop_pct = (entry - stop) / entry * 100
        size = min(capital * risk / (stop_pct / 100), capital * max_frac)
        plans.append({
            "symbol": sym.replace("USDT", ""), "state": state, "in_universe": in_uni,
            "price": close, "entry": round(entry, 8), "distance_pct": round(dist, 2) if state != "enter_now" else 0.0,
            "stop": round(stop, 8), "stop_pct": round(stop_pct, 2),
            "trail_atr": round(stop_mult * a, 8), "exit_ema20": round(ema20_, 8),
            "size_usdt": round(size, 2), "risk_usdt": round(capital * risk, 2),
            "how_to_enter": (f"ซื้อเมื่อแท่ง 4h ปิดเหนือ {px(trigger)}" if state != "enter_now" else "สัญญาณเกิดแล้วบนแท่ง 4h ล่าสุด → เข้าที่ราคาตลาด")
                            + ("" if btc_up else f" และ BTC ต้องกลับขึ้นเหนือ EMA200 ก่อน"),
            "how_to_exit": f"ขายเมื่อแท่ง 4h ปิดต่ำกว่า EMA20 (~{px(ema20_)}) หรือโดน stop {px(stop)} "
                           f"(กำไรถึง {px(entry + stop_mult * a)} = 1R → เลื่อน stop มาที่ทุน แล้วขยับตามราคาปิดสูงสุด − {px(stop_mult * a)})",
            "note": "" if in_uni else "นอก Top 20 — ยังไม่ผ่าน backtest ความเสี่ยงสูงกว่า",
        })
    order = {"enter_now": 0, "near": 1, "wait_btc": 2}
    plans.sort(key=lambda p: (order[p["state"]], not p["in_universe"], p["distance_pct"]))
    return plans[:40]


def alert_new(plans: list[dict], bar: str) -> list[dict]:
    """ส่ง Telegram เมื่อมีแผน 'เข้าได้ตอนนี้' ใหม่ (ส่งครั้งเดียวต่อเหรียญต่อแท่ง)."""
    seen = json.loads(ALERTS.read_text()) if ALERTS.exists() else {}
    new = [p for p in plans if p["state"] == "enter_now" and seen.get(p["symbol"]) != bar]
    if not new:
        return []
    from lab.notifier import Notifier
    n = Notifier(telegram=True)
    for p in new:
        n.send(f"📈 แผนเทรด {p['symbol']}{' (นอก Top 20)' if not p['in_universe'] else ''}\n"
               f"เข้า: ~{px(p['entry'])} | Stop: {px(p['stop'])} (−{p['stop_pct']:.1f}%)\n"
               f"ขนาด: ~{p['size_usdt']:,.0f} USDT (เสี่ยง {p['risk_usdt']:.1f} USDT ถ้าโดน stop)\n"
               f"ออก: {p['how_to_exit']}\n"
               "⚠️ ตามกฎที่ผ่าน backtest ไม่ใช่การรับประกันกำไร")
        seen[p["symbol"]] = bar
    ALERTS.parent.mkdir(exist_ok=True)
    ALERTS.write_text(json.dumps(seen))
    return new
