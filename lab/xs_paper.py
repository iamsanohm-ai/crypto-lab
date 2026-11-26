"""บัญชีจำลอง "Long แข็ง / Short อ่อน" (cross-sectional momentum แบบรวม 12 ชุดพารามิเตอร์) — รันวันละครั้งในรอบบอท.

12 พอร์ตย่อย (L ∈ {7,14,30} วัน × H ∈ {7,14} วัน × N ∈ {3,5}) แต่ละพอร์ตได้ทุน 1/12 และปรับพอร์ตทุก H วันตามรอบของตัวเอง
น้ำหนักสุทธิต่อเหรียญ = เฉลี่ยของ 12 พอร์ต (ผลรวม |น้ำหนัก| ≈ 1 = ใช้เงินเต็ม 1 เท่า, ครึ่ง long ครึ่ง short)
ผลทดสอบ OOS (research/xs_momentum.json + ens): +145% Sharpe 1.42 DD −33% · ตลาดขาลง +30% · ปี 2026 +19.3%
⚠️ บัญชีจำลองใช้ราคา spot แทน perpetual (ต่างกันเล็กน้อย) และยังไม่รวม funding (ทดสอบย้อนหลังรวมแล้ว) — ส่งออเดอร์จริงได้จากคอมเจ้าของเท่านั้น
python -m lab.xs_paper
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

import numpy as np

from lab.data import ROOT, now_iso
from lab.live import build_live_market

CONFIGS = list(itertools.product((7, 14, 30), (7, 14), (3, 5)))
COST = 0.001                      # fee 0.05% + slippage 0.05% ต่อข้าง (taker)
STATE, PUB = ROOT / "state" / "xs.json", ROOT / "docs" / "xs_paper.json"
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def universe() -> list[str]:
    f = ROOT / "state" / "paper_keltner_trend.json"
    return (json.loads(f.read_text()).get("universe") or {}).get("members", []) if f.exists() else []


def sub_weights(closes: dict[str, np.ndarray], L: int, N: int) -> dict[str, float]:
    lb = L * 6
    mom = {s: c[-1] / c[-1 - lb] - 1 for s, c in closes.items() if len(c) > lb and c[-1 - lb] > 0 and not np.isnan(c[-1 - lb])}
    if len(mom) < 2 * N + 2:
        return {}
    r = sorted(mom, key=mom.get)
    w = {s: -0.5 / N for s in r[:N]}
    for s in r[-N:]: w[s] = w.get(s, 0) + 0.5 / N
    return w


def run(force: bool = False):
    st = json.loads(STATE.read_text()) if STATE.exists() else {"capital": 500.0, "equity": 500.0, "subs": {}, "weights": {}, "last_day": None,
                                                               "prices": {}, "log": [], "curve": [], "started_at": now_iso(), "fees_usdt": 0.0}
    today = datetime.now(timezone.utc).date()
    if st["last_day"] == str(today) and not force:
        print("xs: วันนี้ประมวลผลแล้ว"); return st
    uni = universe()
    m = build_live_market(uni, bars=200, with_funding=False)
    closes = {s: m.close[:, j][~np.isnan(m.close[:, j])] for j, s in enumerate(m.symbols) if s in uni}
    px = {s: float(c[-1]) for s, c in closes.items() if len(c)}
    # 1) ผลตอบแทนตั้งแต่ครั้งก่อนจากน้ำหนักเดิม
    if st["weights"] and st["prices"]:
        r = sum(w * (px.get(s, st["prices"].get(s)) / st["prices"][s] - 1) for s, w in st["weights"].items() if s in st["prices"])
        st["equity"] *= 1 + r
        st["log"].append({"t": now_iso(), "kind": "pnl", "pct": round(r * 100, 3)})
    # 2) พอร์ตย่อยที่ถึงรอบปรับ
    day_n = (datetime.now(timezone.utc) - EPOCH).days
    for L, H, N in CONFIGS:
        k = f"L{L}H{H}N{N}"
        if k not in st["subs"] or day_n % H == 0:
            st["subs"][k] = sub_weights(closes, L, N)
    net: dict[str, float] = {}
    for w in st["subs"].values():
        for s, x in w.items(): net[s] = net.get(s, 0) + x / len(CONFIGS)
    net = {s: round(x, 5) for s, x in net.items() if abs(x) > 1e-6}
    turnover = sum(abs(net.get(s, 0) - st["weights"].get(s, 0)) for s in set(net) | set(st["weights"]))
    fee = st["equity"] * turnover * COST; st["equity"] -= fee; st["fees_usdt"] += fee
    st["weights"], st["prices"], st["last_day"], st["updated_at"] = net, px, str(today), now_iso()
    st["curve"].append([now_iso(), round(st["equity"], 3)]); st["curve"] = st["curve"][-800:]
    st["log"].append({"t": now_iso(), "kind": "rebalance", "turnover": round(turnover, 3), "fee_usdt": round(fee, 4)}); st["log"] = st["log"][-300:]
    mom30 = {s: round((c[-1] / c[-181] - 1) * 100, 1) for s, c in closes.items() if len(c) > 181}
    st["targets"] = sorted([{"symbol": s, "weight": w, "side": "long" if w > 0 else "short", "mom30_pct": mom30.get(s)} for s, w in net.items()], key=lambda x: -x["weight"])
    STATE.parent.mkdir(exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1)); PUB.write_text(json.dumps(st, ensure_ascii=False))
    print(f"xs: equity {st['equity']:.2f} · long {[t['symbol'] for t in st['targets'] if t['weight'] > 0]} · short {[t['symbol'] for t in st['targets'] if t['weight'] < 0]}")
    return st


if __name__ == "__main__":
    import sys
    run(force="--force" in sys.argv)
