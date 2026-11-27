"""สมองความน่าจะเป็น + สภากลยุทธ์ + การเรียนรู้จากคำทำนายของตัวเอง (เรียกจาก scanner ทุกรอบ).

1) ความน่าจะเป็น: ต่อเหรียญ (ที่ซื้อขายคล่อง) จำลอง 2,000 อนาคต 7 วัน ด้วย block bootstrap จากผลตอบแทน 4 ชม. จริง 50 วันล่าสุด
   (สุ่มทีละบล็อก 1 วัน เพื่อเก็บลักษณะการเคลื่อนไหวต่อเนื่อง) → P(ขึ้นใน 7 วัน), ช่วงผลตอบแทน 5–95%,
   แผนซื้อ: stop 3×ATR / เป้า 2R → P(ถึงเป้าก่อน stop), ค่าคาดหวัง · แผน short แบบกระจก
   ⚠️ เป็นการจำลองจากอดีตล่าสุด ไม่ใช่การรู้อนาคต — ระบบจึงตรวจความแม่นของตัวเองในข้อ 3
2) สภากลยุทธ์: ทุกวิธีในระบบโหวต (บอทหลัก, บอทกล้า, Long แข็ง/Short อ่อน, ORB, ความน่าจะเป็น) → มติ ซื้อ / short / รอ พร้อมเหตุผล
3) เรียนรู้: บันทึกคำทำนาย P(ขึ้น 7 วัน) วันละครั้ง → ครบ 7 วันตรวจผลจริง → Brier score + ตารางความแม่นตามช่วงความมั่นใจ
   → ปรับความน่าจะเป็นครั้งต่อไปเข้าหาความถี่จริง (ยิ่งมีหลักฐานมาก ยิ่งปรับมาก)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from lab.data import ROOT, now_iso

PATHS, HORIZON, BLOCK, HIST = 2000, 42, 6, 300
PRED = ROOT / "state" / "predictions.jsonl"
BINS = [0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.01]


def simulate(close: np.ndarray, atr: float, rng, demean: bool = False) -> dict | None:
    c = close[~np.isnan(close)][-HIST:]
    if len(c) < 120 or not atr or atr <= 0:
        return None
    r = np.diff(np.log(c))
    if demean:
        r = r - r.mean()          # สถานการณ์ "ไม่มีเทรนด์": เก็บความผันผวนจริง แต่ตัดแนวโน้มออก
    nb = HORIZON // BLOCK
    starts = rng.integers(0, len(r) - BLOCK, size=(PATHS, nb))
    path = r[starts[..., None] + np.arange(BLOCK)].reshape(PATHS, HORIZON)
    cum = np.cumsum(path, axis=1)
    px = c[-1] * np.exp(cum)
    fin = px[:, -1] / c[-1] - 1
    d = 3 * atr; out = {"p_up7": float((fin > 0).mean()), "p5": float(np.percentile(fin, 5) * 100), "p50": float(np.median(fin) * 100),
                        "p95": float(np.percentile(fin, 95) * 100)}
    for side, sgn in (("long", 1), ("short", -1)):
        stop, tgt = c[-1] - sgn * d, c[-1] + sgn * 2 * d
        hit_t = (px >= tgt) if sgn > 0 else (px <= tgt)
        hit_s = (px <= stop) if sgn > 0 else (px >= stop)
        ft = np.where(hit_t.any(1), hit_t.argmax(1), HORIZON + 1); fs = np.where(hit_s.any(1), hit_s.argmax(1), HORIZON + 1)
        win, lose = ft < fs, fs < ft
        ret = np.where(win, 2 * d / c[-1], np.where(lose, -d / c[-1], sgn * fin))   # หน่วย: ผลตอบแทนต่อราคา
        cost = 0.003 if sgn > 0 else 0.002
        out[side] = {"p_target": float(win.mean()), "p_stop": float(lose.mean()), "ev_pct": float((ret.mean() - cost) * 100)}
    return out


def calibration() -> dict:
    """ตรวจคำทำนายที่ครบ 7 วันแล้ว (บันทึกผลจริงไว้ในไฟล์)."""
    if not PRED.exists():
        return {"n": 0}
    recs = [json.loads(x) for x in PRED.read_text().splitlines() if x.strip()]
    done = [r for r in recs if r.get("outcome") is not None]
    if not done:
        return {"n": 0, "pending": len(recs)}
    p = np.array([r["p"] for r in done]); y = np.array([r["outcome"] for r in done], float)
    table = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        mk = (p >= lo) & (p < hi)
        if mk.sum(): table.append({"bin": f"{int(lo * 100)}–{int(min(hi, 1) * 100)}%", "n": int(mk.sum()), "pred": round(float(p[mk].mean()), 3), "real": round(float(y[mk].mean()), 3)})
    base = float(y.mean())
    return {"n": int(len(done)), "pending": int(len(recs) - len(done)), "brier": round(float(((p - y) ** 2).mean()), 4),
            "brier_naive": round(float(((base - y) ** 2).mean()), 4), "hit_rate": round(float(((p > 0.5) == (y > 0.5)).mean()), 3), "table": table}


def calibrate(p: float, cal: dict) -> float:
    """ปรับเข้าหาความถี่จริงของช่วงเดียวกัน: น้ำหนัก n/(n+50)."""
    for b in cal.get("table", []):
        lo, hi = [int(x) / 100 for x in b["bin"].rstrip("%").split("–")]
        if lo <= p < max(hi, 1.01 if hi >= 1 else hi):
            w = b["n"] / (b["n"] + 50); return (1 - w) * p + w * (p + b["real"] - b["pred"])
    return p


def record_and_score(m, preds: dict[str, float]):
    """บันทึกคำทำนายวันละครั้ง และให้คะแนนรายการที่ครบ 7 วัน."""
    now = datetime.now(timezone.utc); today = now.strftime("%Y-%m-%d")
    recs = [json.loads(x) for x in PRED.read_text().splitlines() if x.strip()] if PRED.exists() else []
    col = {s: j for j, s in enumerate(m.symbols)}
    for r in recs:
        if r.get("outcome") is None and (now - datetime.fromisoformat(r["t"])).days >= 7 and r["sym"] in col:
            c = m.close[:, col[r["sym"]]]; last = c[~np.isnan(c)][-1]
            r["outcome"] = int(last > r["price"]); r["realized_pct"] = round(float(last / r["price"] - 1) * 100, 2)
    if not any(r["t"][:10] == today for r in recs):
        for s, (p, price) in preds.items():
            recs.append({"t": now.isoformat(timespec="seconds"), "sym": s, "p": round(p, 4), "price": price})
    recs = recs[-20000:]
    PRED.parent.mkdir(exist_ok=True); PRED.write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def council(row: dict, pr: dict | None, think: dict | None, xs_w: float | None, btc_up: bool) -> dict:
    v = []
    if think: v.append(("บอทหลัก (Keltner)", {"enter": 1, "hold": 1, "wait": 0, "no": -1}.get(think["verdict"], 0), think["headline"]))
    else: v.append(("บอทหลัก (Keltner)", 0 if (row.get("vs_ema200_pct") or -1) > 0 else -1, "ยังไม่เข้าเงื่อนไข" if (row.get("vs_ema200_pct") or -1) > 0 else "อยู่ใต้ EMA200"))
    strong = (row.get("mom_30d_pct") or -99) > 0
    v.append(("บอทกล้า", 1 if row.get("status") == "buy_signal" and strong else 0, "เหรียญแข็ง + ทะลุกรอบ" if strong else "ไม่แข็งพอ"))
    if xs_w: v.append(("Long แข็ง/Short อ่อน", 1 if xs_w > 0 else -1, f"{'long' if xs_w > 0 else 'short'} {abs(xs_w) * 100:.1f}% ของพอร์ต"))
    sc = row.get("score") or 0
    v.append(("ORB คะแนน", 1 if sc >= 70 else -1 if sc < 30 else 0, f"คะแนน {sc}"))
    if pr:
        fl = pr.get("flat") or {}
        el, es = min(pr["long"]["ev_pct"], fl.get("long_ev", 9)), min(pr["short"]["ev_pct"], fl.get("short_ev", 9))   # ระวัง: ต้องดีทั้งสองสถานการณ์
        v.append(("จำลองความน่าจะเป็น", 1 if el > 0.3 and el > es else -1 if es > 0.3 else 0, f"P(ขึ้น 7 วัน) เทรนด์ต่อ {pr['p_up7'] * 100:.0f}% / ไม่มีเทรนด์ {fl.get('p_up7', 0) * 100:.0f}% · คาดหวังกรณีแย่กว่า long {el:+.2f}% / short {es:+.2f}%"))
    score = sum(x[1] for x in v)
    verdict = "ซื้อ" if score >= 2 and btc_up else "short" if score <= -3 else "รอ"
    return {"votes": [{"who": a, "vote": b, "why": c} for a, b, c in v], "score": score, "verdict": verdict}


def run(m, rows: list[dict], thinking: dict | None, btc_up: bool) -> dict:
    from lab.strategies import atr
    rng = np.random.default_rng(int(datetime.now(timezone.utc).timestamp()) // 900)
    A = atr(m, 20).to_numpy(); col = {s: j for j, s in enumerate(m.symbols)}
    T = {x["symbol"]: x for x in ((thinking or {}).get("items") or [])}
    xs = {}
    f = ROOT / "state" / "xs.json"
    if f.exists():
        xs = {t["symbol"][:-4]: t["weight"] for t in json.loads(f.read_text()).get("targets", [])}
    cal = calibration(); out = {}; preds = {}
    for r in rows:
        if r.get("status") == "illiquid":
            continue
        j = col.get(r["symbol"] + "USDT")
        if j is None:
            continue
        pr = simulate(m.close[:, j], float(np.nan_to_num(A[-1, j])), rng)
        flat = simulate(m.close[:, j], float(np.nan_to_num(A[-1, j])), rng, demean=True)
        if pr and flat:
            pr["flat"] = {"p_up7": flat["p_up7"], "p5": flat["p5"], "p95": flat["p95"], "long_ev": flat["long"]["ev_pct"], "short_ev": flat["short"]["ev_pct"],
                          "long_p_target": flat["long"]["p_target"], "long_p_stop": flat["long"]["p_stop"]}
            pr["p_up7_raw"] = pr["p_up7"]; pr["p_up7"] = float(np.clip(calibrate(pr["p_up7"], cal), 0.01, 0.99))
            preds[r["symbol"] + "USDT"] = (pr["p_up7_raw"], float(m.close[-1, j]))
        cn = council(r, pr, T.get(r["symbol"]), xs.get(r["symbol"]), btc_up)
        out[r["symbol"]] = {"prob": pr and {k: (round(v, 4) if isinstance(v, float) else {kk: round(vv, 4) for kk, vv in v.items()}) for k, v in pr.items()} if pr else None, "council": cn}
    try:
        record_and_score(m, preds)
    except Exception as e:  # noqa: BLE001
        print("prediction log failed", e)
    cal = calibration()          # สถานะล่าสุดหลังบันทึก/ตรวจรอบนี้ (ใช้แสดงผล)
    best_long = sorted(((s, x) for s, x in out.items() if x["prob"]), key=lambda kv: -kv[1]["prob"]["long"]["ev_pct"])[:5]
    best_short = sorted(((s, x) for s, x in out.items() if x["prob"]), key=lambda kv: -kv[1]["prob"]["short"]["ev_pct"])[:5]
    return {"generated_at": now_iso(), "paths": PATHS, "horizon_days": HORIZON // 6, "coins": out, "calibration": cal,
            "best_long": [{"symbol": s, **x["prob"]["long"], "p_up7": x["prob"]["p_up7"]} for s, x in best_long],
            "best_short": [{"symbol": s, **x["prob"]["short"], "p_up7": x["prob"]["p_up7"]} for s, x in best_short],
            "simulated_futures": len([1 for x in out.values() if x["prob"]]) * PATHS}
