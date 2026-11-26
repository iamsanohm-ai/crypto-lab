"""บัญชีจำลอง "เก็บ funding" (ซื้อ spot + short perp เท่ากัน) — รันในรอบบอท ทำงานหลังรอบ funding ทุก 8 ชม. (00/08/16 UTC).

กฎเดียวกับที่ทดสอบ (research/edge_search.json, limit order + ส่วนลด BNB):
  เข้า: funding เฉลี่ย 9 รอบล่าสุด (3 วัน) > 0.01%/รอบ · เลือกสูงสุด 5 เหรียญจาก Top 20 · 100 USDT ต่อขา ต่อเหรียญ
  ออก: funding เฉลี่ย ≤ 0 หรือหลุด Top 20 · ค่าธรรมเนียมเปิด/ปิด 2 ขา = (0.075% + 0.02%) ต่อขา ต่อครั้ง
⚠️ funding: เซิร์ฟเวอร์ (สหรัฐฯ) เข้า Binance Futures ไม่ได้ จึงใช้ค่าจริงรายเดือนเมื่อมี และ *ประมาณการ* จาก premium index รายวัน
   ซึ่งช้าประมาณ 1 วัน — ทุกรายการบันทึกว่าเป็นค่าจริงหรือประมาณการ
python -m lab.carry
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from lab.data import ROOT, now_iso
from lab.live import funding_recent

ENTER, EXIT, MAXC, ALLOC = 0.0001, 0.0, 5, 100.0
FEE_LEG = 0.00075 + 0.0002          # spot maker (BNB) + futures maker (BNB) ต่อการเปิดหรือปิด 1 ครั้ง (ทั้งสองขา)
STATE, PUB = ROOT / "state" / "carry.json", ROOT / "docs" / "carry_paper.json"


def universe() -> list[str]:
    f = ROOT / "state" / "paper_keltner_trend.json"
    return (json.loads(f.read_text()).get("universe") or {}).get("members", []) if f.exists() else []


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"capital": 500.0, "cash": 500.0, "held": {}, "log": [], "last_event": None,
                                                                  "funding_usdt": 0.0, "fees_usdt": 0.0, "started_at": now_iso()}


def run(force: bool = False):
    st = load(); now = datetime.now(timezone.utc)
    event = now.replace(minute=0, second=0, microsecond=0, hour=now.hour // 8 * 8).isoformat()
    if st["last_event"] == event and not force:
        print("carry: รอบ funding นี้ประมวลผลแล้ว"); return st
    uni = universe(); rates = {}
    for sym in uni:
        try:
            f = funding_recent(sym)
        except Exception as e:  # noqa: BLE001
            print("funding", sym, e); continue
        if len(f):
            last9 = f.tail(9)
            rates[sym] = {"avg": float(last9.funding.mean()), "last": float(f.funding.iloc[-1]), "estimated": bool(last9.estimated.any()),
                          "as_of": str(f.t.iloc[-1])}
    # 1) รับ funding ของรอบที่เพิ่งผ่าน สำหรับเหรียญที่ถืออยู่ (ใช้ค่าล่าสุดที่มี)
    for sym in list(st["held"]):
        r = rates.get(sym)
        if r:
            amt = ALLOC * r["last"]; st["cash"] += amt; st["funding_usdt"] += amt
            st["log"].append({"t": event, "sym": sym, "kind": "funding", "rate": r["last"], "usdt": round(amt, 5), "estimated": r["estimated"]})
    # 2) ปรับพอร์ตตามกฎ
    want = [s for s, r in sorted(rates.items(), key=lambda kv: -kv[1]["avg"]) if r["avg"] > ENTER][:MAXC]
    for sym in list(st["held"]):
        r = rates.get(sym)
        if sym not in uni or (r and r["avg"] <= EXIT):
            fee = ALLOC * FEE_LEG; st["cash"] -= fee; st["fees_usdt"] += fee; del st["held"][sym]
            st["log"].append({"t": event, "sym": sym, "kind": "close", "why": "หลุด Top 20" if sym not in uni else f"funding เฉลี่ย {r['avg'] * 100:.4f}% ≤ 0", "usdt": -round(fee, 4)})
    for sym in want:
        if sym in st["held"] or len(st["held"]) >= MAXC:
            continue
        fee = ALLOC * FEE_LEG; st["cash"] -= fee; st["fees_usdt"] += fee
        st["held"][sym] = {"opened": event, "avg_at_open": rates[sym]["avg"]}
        st["log"].append({"t": event, "sym": sym, "kind": "open", "why": f"funding เฉลี่ย 3 วัน {rates[sym]['avg'] * 100:.4f}%/รอบ (≈{rates[sym]['avg'] * 3 * 365 * 100:.1f}%/ปี)", "usdt": -round(fee, 4)})
    st["log"] = st["log"][-400:]; st["last_event"] = event; st["updated_at"] = now_iso()
    st["rates"] = {s: {k: (round(v, 7) if isinstance(v, float) else v) for k, v in r.items()} for s, r in rates.items()}
    st["equity"] = round(st["cash"], 4)
    STATE.parent.mkdir(exist_ok=True); STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    PUB.write_text(json.dumps(st, ensure_ascii=False))
    print(f"carry: ถือ {list(st['held'])} · equity {st['equity']:.2f} · funding {st['funding_usdt']:+.3f} · fees {st['fees_usdt']:.3f}")
    return st


if __name__ == "__main__":
    import sys
    run(force="--force" in sys.argv)
