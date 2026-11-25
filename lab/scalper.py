"""เทรดเร็ว/ระยะสั้น แบบ paper บนราคาจริงของ Binance — "สนามประลองกลยุทธ์" วิ่งต่อเนื่องตลอดเวลาที่ bot-loop ทำงาน.

หลายกลยุทธ์ (5 นาที จาก scalp_research + 1 ชั่วโมง จาก short_research) ถูกเทรดเงาพร้อมกันด้วยราคาจริง
แต่ละกลยุทธ์มี "ประตู" ของตัวเอง: ใช้เงินได้เฉพาะตัวที่ผลเงา 30 ครั้งล่าสุดเป็นบวกหลังค่าธรรมเนียม

ระบบ "เรียนรู้" แบบซื่อตรง:
  1. ทุกสัญญาณถูกเทรดแบบ "เงา" (shadow) เสมอ — ไม่ใช้เงิน แต่จดผลจริงจากราคาจริง หลังหักค่าธรรมเนียม
  2. ใช้เงิน (paper) ก็ต่อเมื่อผลเงา 30 ครั้งล่าสุด "เฉลี่ยเป็นบวกหลังค่าธรรมเนียม" เท่านั้น — ถ้าตลาดเปลี่ยนจนขาดทุน ระบบหยุดใช้เงินเอง
  3. Sentinel: ขาดทุน -3% ในวัน หรือแพ้ติด 3 ครั้ง หรือราคาค้าง → หยุดถึงวันถัดไป (paper)
ราคาเข้า/ออกเป็นการจำลอง (ราคาล่าสุด ± slippage 0.05% + ค่าธรรมเนียม 0.1% ต่อข้าง) — ไม่ใช่การจับคู่จริงในตลาด
ไม่มีการส่งออเดอร์จริง: เงินจริงต้องให้เจ้าของพิมพ์ "go live" และอนุมัติทุกออเดอร์

python -m lab.scalper --dir /tmp/scalp --minutes 340
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lab.data import API, ROOT, _get, now_iso
from lab.scalp_research import COINS, FEE, SLIP, ema, rsi, signals
from lab.short_research import signals1h

CAPITAL, RISK, MAX_NOTIONAL, MAX_POS = 500.0, 0.005, 125.0, 3
RISK_PROBATION = 0.0025          # ช่วงทดลอง: ใช้เงินจริงในบัญชีจำลองครึ่งหนึ่งของปกติ จนกว่าผลจะพิสูจน์ว่าเป็นบวก
BENCH_N, BENCH_MIN = 20, -0.003  # ใช้เงิน 20 ครั้งล่าสุดเฉลี่ยแย่กว่า -0.4% → พักใช้เงิน กลับไปเทรดเงาจนกว่าผลเงาจะเป็นบวก
# ทดสอบ 5m จริง 180 วัน: ตัวที่ดีที่สุดใน 120 วันแรก (ขึ้น >2% ใน 1 ชม., เป้า +3%, stop −0.8% แบบขยับตาม) ยังขาดทุน −0.42%/เทรด ใน 60 วันล่าสุด
# → เทรดด้วยเงินจำลองครึ่งขนาด (ตามที่เจ้าของขอ 2026-11-25) และพักเองเมื่อผล 20 ครั้งล่าสุดแย่กว่า BENCH_MIN
ROTATION = {"strategy": "momentum_rotation", "params": {"lb": 12, "th": 0.02, "volk": 1.5}, "exit": {"tp": 0.03, "sl": 0.008, "trail": 0.008, "hold": 36},
            "research": {"oos_avg_pct": -0.416, "oos_gross_pct": None, "oos_trades": 95}}
GATE_N, GATE_MIN = 30, 0.0005
POLL = 15


def pick() -> dict:
    f = ROOT / "research" / "scalp_research.json"
    r = json.loads(f.read_text())["pick"] if f.exists() else None
    return r or {"strategy": "momo_burst", "params": {"n": 36, "k": 3.0}, "exit": {"tp": 0.025, "sl": 0.012, "hold": 12}}


LABEL = {"momo_burst": "ทะลุจุดสูง + volume พุ่ง", "rsi2_dip": "ซื้อตอนย่อแรง (RSI2)", "ema_cross": "EMA9 ตัด EMA21",
         "bb_bounce": "เด้งจากขอบล่าง Bollinger", "trend_pullback": "ซื้อตอนย่อในขาขึ้น", "range_breakout": "ทะลุกรอบ + volume",
         "vol_breakout": "Volatility breakout", "dip_reversal": "ร่วงแรงแล้วรอเด้ง", "momentum_rotation": "หมุนเลือกเหรียญที่กำลังวิ่ง"}
SEC = {"5m": 300, "1h": 3600}


def models() -> list[dict]:
    """กลยุทธ์ที่ลงสนาม: ตัวที่ดีที่สุดของ 5 นาที + ตัวที่ดีที่สุดของแต่ละแบบบน 1 ชั่วโมง (จากการทดสอบย้อนหลังล่าสุด)."""
    p5 = pick(); out = [{"id": "5m:momentum_rotation", "interval": "5m", "active": True, **ROTATION},
                        {"id": "5m:" + p5["strategy"], "interval": "5m", **{k: p5[k] for k in ("strategy", "params", "exit")}}]
    f = ROOT / "research" / "short_research.json"
    if f.exists():
        for b in json.loads(f.read_text()).get("best_per_strategy", []):
            out.append({"id": "1h:" + b["strategy"], "interval": "1h", "strategy": b["strategy"], "params": b["params"], "exit": b["exit"],
                        "research": {"oos_avg_pct": b["oos"]["avg_pct"], "oos_gross_pct": b["oos_gross"]["avg_pct"], "oos_trades": b["oos"]["trades"]}})
    r5 = ROOT / "research" / "scalp_research.json"
    if r5.exists():
        pk = json.loads(r5.read_text())["pick"]; out[1]["research"] = {"oos_avg_pct": pk["oos"]["avg_pct"], "oos_gross_pct": pk["oos_gross"]["avg_pct"], "oos_trades": pk["oos"]["trades"]}
    for m in out:
        m["label"] = f"{m['interval'].replace('5m', '5 นาที').replace('1h', '1 ชม.')} · {LABEL.get(m['strategy'], m['strategy'])}"
    return out


def bars1h(sym: str) -> pd.DataFrame:
    raw = json.loads(_get(f"{API}/klines?symbol={sym}USDT&interval=1h&limit=260"))
    df = pd.DataFrame(raw, columns=list(range(12)))
    df = pd.DataFrame({"time": pd.to_datetime(df[0].astype("int64"), unit="ms", utc=True), "open": df[1].astype(float), "high": df[2].astype(float),
                       "low": df[3].astype(float), "close": df[4].astype(float), "volume": df[5].astype(float), "ms": df[0].astype("int64")})
    return df[df.ms + 3_600_000 <= time.time() * 1000].reset_index(drop=True)


def watchlist() -> list[str]:
    """12 เหรียญหลัก + Top 20 ตามสภาพคล่องเดือนนี้ (ให้บอทเลือกเหรียญที่กำลังวิ่งจากกลุ่มที่ซื้อขายคล่อง)."""
    f = ROOT / "state" / "paper_keltner_trend.json"
    uni = (json.loads(f.read_text()).get("universe") or {}).get("members", []) if f.exists() else []
    return list(dict.fromkeys(COINS + [u[:-4] for u in uni if u.endswith("USDT")]))


def prices(coins: list[str] | None = None) -> dict[str, float]:
    syms = json.dumps([c + "USDT" for c in (coins or COINS)], separators=(",", ":"))
    raw = _get(f"{API}/ticker/price?symbols={syms}")
    return {d["symbol"][:-4]: float(d["price"]) for d in json.loads(raw)}


def bars5(sym: str) -> pd.DataFrame:
    raw = json.loads(_get(f"{API}/klines?symbol={sym}USDT&interval=5m&limit=260"))
    df = pd.DataFrame(raw, columns=list(range(12)))
    df = pd.DataFrame({"time": df[0].astype("int64"), "open": df[1].astype(float), "high": df[2].astype(float),
                       "low": df[3].astype(float), "close": df[4].astype(float), "volume": df[5].astype(float)})
    return df[df.time + 300_000 <= time.time() * 1000].reset_index(drop=True)   # เฉพาะแท่งที่ปิดแล้ว


def note(df: pd.DataFrame, P: dict) -> dict:
    """สถานะของเหรียญตามเงื่อนไขกลยุทธ์ (ให้หน้าเว็บอ่านง่าย)."""
    c = df.close.to_numpy(); e200 = ema(c, 200)[-1]
    out = {"trend_up": bool(c[-1] > e200), "vs_ema200_pct": round((c[-1] / e200 - 1) * 100, 2)}
    s, p = P["strategy"], P["params"]
    if s == "momo_burst":
        hh = df.high.iloc[-p["n"] - 1:-1].max(); va = df.volume.iloc[-21:-1].mean()
        out.update(to_break_pct=round((hh / c[-1] - 1) * 100, 2), vol_x=round(float(df.volume.iloc[-1] / va), 2) if va else None)
    elif s == "rsi2_dip":
        out.update(rsi2=round(float(rsi(c, 2)[-1]), 1))
    return out


class Scalper:
    def __init__(self, d: Path):
        self.f = d / "scalper.json"
        seed = self.f if self.f.exists() else ROOT / "state" / "scalper.json"
        self.s = json.loads(seed.read_text()) if seed.exists() else {
            "capital": CAPITAL, "cash": CAPITAL, "positions": [], "shadow": [], "shadow_closed": [], "trades": [],
            "curve": [], "events": [], "started_at": now_iso(),
            "sentinel": {"day": None, "day_start_equity": CAPITAL, "loss_streak": 0, "halted": None}}
        self.MODELS = models(); self.P = self.MODELS[0]; self.s["model"] = self.P; self.s["models"] = self.MODELS
        self.coins = watchlist(); self.s["coins"] = self.coins
        self.px: dict[str, float] = {}; self.px_at = 0.0; self.last_bar = self.s.get("last_bar") or 0; self.last_hour = self.s.get("last_hour") or 0

    # ---------- helpers ----------
    def ev(self, text: str, kind: str = "info"):
        self.s["events"] = ([{"t": now_iso(), "text": text, "kind": kind}] + self.s["events"])[:80]
        print(now_iso(), text, flush=True)
        if kind in ("buy", "sell", "halt"):
            try:
                from lab.notifier import Notifier
                Notifier(telegram=True).send("[Crypto Lab · เทรดเร็ว paper] " + text)
            except Exception:
                pass

    def equity(self) -> float:
        return self.s["cash"] + sum(p["qty"] * self.px.get(p["sym"], p["entry"]) for p in self.s["positions"])

    def gates(self) -> dict:
        G = {m["id"]: self.gate(m["id"]) for m in self.MODELS}
        self.s["gates"] = G
        opened = [g for g in G.values() if g["open"]]
        self.s["gate"] = max(opened, key=lambda g: g["avg_pct"]) if opened else max(G.values(), key=lambda g: (g["n"], g["avg_pct"] or -9))
        return G

    def gate(self, mid: str | None = None) -> dict:
        mid = mid or self.MODELS[0]["id"]
        last = [x["net_pct"] for x in self.s["shadow_closed"] if x.get("model", self.MODELS[0]["id"]) == mid][:GATE_N]
        avg = float(np.mean(last)) / 100 if last else None
        g = {"n": len(last), "need": GATE_N, "avg_pct": None if avg is None else round(avg * 100, 3),
             "win_pct": round(float(np.mean([x > 0 for x in last]) * 100), 1) if last else None,
             "open": len(last) >= GATE_N and avg > GATE_MIN, "model": mid}
        return g

    def money_mode(self, m: dict, g: dict) -> str:
        """full = ผลเงาพิสูจน์แล้วว่าเป็นบวก · probation = บอทหลักระยะสั้นเทรดเงินเลยแต่ขนาดครึ่ง · shadow = ยังไม่ใช้เงิน/ถูกพัก."""
        mine = [t["net_pct"] for t in self.s["trades"] if t.get("model") == m["id"]][:BENCH_N]
        benched = len(mine) >= BENCH_N and np.mean(mine) / 100 < BENCH_MIN and not g["open"]
        self.s.setdefault("bench", {})[m["id"]] = bool(benched)
        if g["open"]:
            return "full"
        return "probation" if m.get("active") and not benched else "shadow"

    def sentinel_ok(self) -> bool:
        S = self.s["sentinel"]; day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if S["day"] != day:
            S.update(day=day, day_start_equity=round(self.equity(), 4))
            if S["halted"] and S["halted"].get("resume_on", "") <= day:
                S["halted"] = None; S["loss_streak"] = 0; self.ev("Sentinel: วันใหม่ กลับมาเทรดได้", "info")
        if S["halted"]:
            return False
        dd = self.equity() / S["day_start_equity"] - 1
        why = f"ขาดทุนวันนี้ {dd:.2%} ถึงเพดาน -3%" if dd <= -0.03 else f"แพ้ติดกัน {S['loss_streak']} ครั้ง" if S["loss_streak"] >= 3 else None
        if why:
            nxt = (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            S["halted"] = {"at": now_iso(), "reason": why, "resume_on": nxt}
            self.ev(f"Sentinel หยุดเทรดเงิน: {why} — กลับมาวันพรุ่งนี้ 07:00 น.", "halt")
            return False
        return True

    # ---------- exits ----------
    def _close(self, p: dict, px: float, reason: str, shadow: bool):
        exit_px = px * (1 - SLIP)
        net = (exit_px * (1 - FEE)) / (p["entry"] * (1 + FEE)) - 1
        rec = {"sym": p["sym"], "entry": p["entry"], "exit": round(exit_px, 8), "net_pct": round(net * 100, 3), "reason": reason,
               "opened_at": p["opened_at"], "closed_at": now_iso(), "model": p.get("model")}
        if shadow:
            self.s["shadow_closed"] = ([rec] + self.s["shadow_closed"])[:300]
            return
        proceeds = p["qty"] * exit_px * (1 - FEE)
        pnl = proceeds - p["cost"]
        self.s["cash"] += proceeds
        rec.update(qty=p["qty"], pnl_usdt=round(pnl, 4))
        self.s["trades"] = ([rec] + self.s["trades"])[:300]
        S = self.s["sentinel"]; S["loss_streak"] = 0 if pnl > 0 else S["loss_streak"] + 1
        TH = {"tp": "ถึงเป้ากำไร", "sl": "โดน stop", "time": "ครบเวลาถือ", "trail": "stop ตามล็อกกำไร"}
        self.ev(f"[{p.get('label', '')}] ขาย {p['sym']} ที่ {exit_px:.6g} ({TH.get(reason, reason)}) · {'+' if pnl >= 0 else ''}{pnl:.2f} USDT ({net * 100:+.2f}%)", "sell")

    def check_exits(self, highs_lows: dict | None = None):
        now = time.time()
        for shadow, key in ((True, "shadow"), (False, "positions")):
            keep = []
            for p in self.s[key]:
                px = self.px.get(p["sym"]); hit = None
                hl = (highs_lows or {}).get(p["sym"])
                if hl and hl[2] > p["t0"]:                      # แท่ง 5 นาทีที่เพิ่งปิด: เช็ค low ก่อน (ระวัง)
                    if hl[1] <= p["sl"]: hit = (p["sl"], "sl")
                    elif hl[0] >= p["tp"]: hit = (p["tp"], "tp")
                if not hit and px:
                    if px <= p["sl"]: hit = (px, "sl")
                    elif px >= p["tp"]: hit = (px, "tp")
                    elif now >= p["deadline"]: hit = (px, "time")
                if hit and hit[1] == "sl" and p.get("trail") and p["sl"] > p["entry"]: hit = (hit[0], "trail")
                if hit: self._close(p, hit[0], hit[1], shadow)
                else:
                    if px and p.get("trail"):          # trailing stop: ล็อกกำไรเมื่อราคาขึ้น (ไม่เลื่อนลง)
                        p["best"] = max(p.get("best", p["entry"]), px); p["sl"] = max(p["sl"], p["best"] * (1 - p["trail"]))
                    keep.append(p)
            self.s[key] = keep

    # ---------- entries ----------
    def on_bar(self, interval: str = "5m"):
        MS = [m for m in self.MODELS if m["interval"] == interval]
        if not MS and interval != "5m":
            return
        fired = []; hl = {}; watch = {}; dfs = {}
        for sym in (self.coins if interval == "5m" else COINS):
            try:
                dfs[sym] = bars5(sym) if interval == "5m" else bars1h(sym)
            except Exception as e:
                self.ev(f"ดึงแท่ง {interval} ของ {sym} ไม่ได้: {e}", "warn")
        btc_up = None
        if interval == "1h" and "BTC" in dfs:
            bc = dfs["BTC"].close.to_numpy(); btc_up = bc > ema(bc, 200)
        for sym, df in dfs.items():
            if len(df) < 210: continue
            if interval == "5m":
                last = df.iloc[-1]; hl[sym] = (float(last.high), float(last.low), int(last.time) / 1000)
            for m in MS:
                if interval == "5m":
                    sig = signals(df, m["strategy"], m["params"])
                else:
                    bu = btc_up[-len(df):] if btc_up is not None and len(btc_up) >= len(df) else None
                    sig = signals1h(df, m["strategy"], m["params"], bu)
                if sig[-1]:
                    c_ = df.close.to_numpy(); fired.append((m, sym, float(c_[-1] / c_[-13] - 1) if len(c_) > 13 else 0.0))
            if interval == "5m" and MS:
                c_ = df.close.to_numpy()
                watch[sym] = {"signal": any(s_ == sym for _, s_, _r in fired), "r1h_pct": round(float(c_[-1] / c_[-13] - 1) * 100, 2), **note(df, MS[0])}
        if interval == "5m":
            self.check_exits(hl); self.s["watch"] = watch
        chk = self.s.setdefault("checks", {})
        for m in MS:
            f_ = [s_ for mm, s_, _r in fired if mm is m]
            chk[m["id"]] = {"at": now_iso(), "coins": len(dfs), "fired": f_}
        G = self.gates(); ok = self.sentinel_ok()
        fired.sort(key=lambda x: -x[2])           # เหรียญที่วิ่งแรงสุดก่อน
        for m, sym, _r in fired:
            px = self.px.get(sym)
            if not px: continue
            ex, g = m["exit"], G[m["id"]]
            entry = px * (1 + SLIP); t0 = time.time()
            base = {"sym": sym, "entry": round(entry, 8), "tp": entry * (1 + ex["tp"]), "sl": entry * (1 - ex["sl"]), "model": m["id"], "label": m["label"], "trail": ex.get("trail"),
                    "opened_at": now_iso(), "t0": t0, "deadline": t0 + ex["hold"] * SEC[m["interval"]]}
            if not any(p["sym"] == sym and p.get("model") == m["id"] for p in self.s["shadow"]):
                self.s["shadow"].append(dict(base))
            held = any(p["sym"] == sym for p in self.s["positions"])
            mode = self.money_mode(m, g)
            if mode == "shadow":
                self.ev(f"[{m['label']}] สัญญาณ {sym} → เทรดเงา (ยังไม่ใช้เงิน: เก็บผลเงาแล้ว {g['n']}/{GATE_N} ครั้ง"
                        + (f" เฉลี่ย {g['avg_pct']:+.2f}%)" if g['avg_pct'] is not None else ")"), "info"); continue
            if not ok or held or len(self.s["positions"]) >= MAX_POS: continue
            eq = self.equity(); notional = min(eq * (RISK if mode == "full" else RISK_PROBATION) / ex["sl"], MAX_NOTIONAL, self.s["cash"] * 0.98)
            if notional < 5: continue
            qty = notional / (entry * (1 + FEE)); cost = qty * entry * (1 + FEE)
            self.s["cash"] -= cost
            self.s["positions"].append({**base, "qty": qty, "cost": cost, "mode": mode})
            why = f"ขึ้น {_r * 100:+.2f}% ใน 1 ชม. แรงสุดในกลุ่มที่เข้าเงื่อนไข" if m["strategy"] == "momentum_rotation" else "เข้าเงื่อนไขกลยุทธ์"
            self.ev(f"[{m['label']}] ซื้อ {sym} {notional:.2f} USDT ที่ {entry:.6g} · {why} · เป้า +{ex['tp']:.1%} / stop -{ex['sl']:.1%}"
                    + (f" (ขยับตาม −{ex['trail']:.1%})" if ex.get("trail") else "") + (" · ช่วงทดลอง: ใช้เงินครึ่งหนึ่ง" if mode == "probation" else ""), "buy")

    def save(self):
        eq = self.equity()
        self.s["equity"] = round(eq, 4); self.s["prices"] = self.px; self.s["updated_at"] = now_iso(); self.s["last_bar"] = self.last_bar; self.s["last_hour"] = self.last_hour
        tr = self.s["trades"]
        self.s["stats"] = {"trades": len(tr), "wins": sum(t["pnl_usdt"] > 0 for t in tr),
                           "pnl_usdt": round(sum(t["pnl_usdt"] for t in tr), 4), "return_pct": round((eq / self.s["capital"] - 1) * 100, 3),
                           "shadow_trades": len(self.s["shadow_closed"])}
        tmp = self.f.with_suffix(".tmp"); tmp.write_text(json.dumps(self.s, ensure_ascii=False, default=float)); tmp.replace(self.f)

    def step(self):
        try:
            self.px = prices(self.coins); self.px_at = time.time()
        except Exception as e:
            self.ev(f"ราคาค้าง/ดึงไม่ได้: {e}", "warn")
        if time.time() - self.px_at > 120:
            return
        bar = int(time.time() // 300)
        if bar != self.last_bar:
            self.last_bar = bar; self.on_bar("5m")
            hour = int(time.time() // 3600)
            if hour != self.last_hour:
                self.last_hour = hour; self.on_bar("1h")
            c = self.s["curve"]; c.append([int(time.time()), round(self.equity(), 4)]); self.s["curve"] = c[-3000:]
        else:
            self.check_exits()
        self.save()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default=str(ROOT / "state")); ap.add_argument("--minutes", type=float, default=1)
    a = ap.parse_args(); d = Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    bot = Scalper(d); end = time.time() + a.minutes * 60
    bot.ev(f"เริ่มสนามประลอง (paper) · {len(bot.MODELS)} กลยุทธ์: " + ", ".join(m["label"] for m in bot.MODELS))
    while time.time() < end:
        t = time.time()
        try:
            bot.step()
        except Exception as e:
            print("step error", e, flush=True)
        time.sleep(max(1, POLL - (time.time() - t)))


if __name__ == "__main__":
    main()
