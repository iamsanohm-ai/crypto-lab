"""ตัวส่งออเดอร์ "Long แข็ง / Short อ่อน" — รันบนคอมของเจ้าของเท่านั้น (เซิร์ฟเวอร์ GitHub ถูก Binance บล็อก)

ทำอะไร: อ่านพอร์ตเป้าหมายล่าสุดที่ระบบคำนวณ (docs/xs_paper.json บน GitHub Pages, อัปเดตวันละครั้ง)
        → เทียบกับสถานะ futures ที่คุณถืออยู่ → เสนอออเดอร์ที่ต้องปรับ → ถามคุณทีละออเดอร์ (ต้องพิมพ์ yes) → ส่ง MARKET บน USDⓈ-M perpetual

ความปลอดภัย:
  • ค่าเริ่มต้น = โหมดทดลอง (แสดงแผนอย่างเดียว) · ต้องใส่ --live และพิมพ์ yes ทุกออเดอร์
  • --usdt = เงินรวมที่ใช้กับกลยุทธ์นี้ (ครึ่ง long ครึ่ง short) ค่าเริ่มต้น 100 · leverage 1x ต่อเหรียญ
  • ข้ามออเดอร์ที่เล็กกว่า --min (ค่าเริ่มต้น 6 USDT) และไม่แตะเหรียญที่ไม่อยู่ในแผน ยกเว้นต้องปิดสถานะที่ระบบเคยเปิด
  • คีย์: ใช้ไฟล์ carry.env เดียวกับ carry_executor.py (ห้าม commit / ห้ามส่งในแชต) · คีย์ต้องเปิด Futures · ปิด Withdrawals
  • ทดสอบย้อนหลังขาดทุนสะสมสูงสุดได้ถึง −33% (ใช้เงินเต็ม) — เริ่มด้วยเงินน้อย

ใช้งาน:  python xs_executor.py            (ดูแผน)
         python xs_executor.py --live --usdt 100
"""
from __future__ import annotations

import argparse
import json
import urllib.request

from carry_executor import FUT, Client, env, filters, get, step

PLAN = "https://iamsanohm-ai.github.io/crypto-lab/xs_paper.json"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); ap.add_argument("--usdt", type=float, default=100.0)
    ap.add_argument("--min", type=float, default=6.0); a = ap.parse_args()
    with urllib.request.urlopen(PLAN + "?t=1", timeout=20) as r:
        plan = json.loads(r.read())
    print(f"แผนล่าสุดของระบบ: {plan.get('last_day')} (บัญชีจำลอง {plan.get('equity', 0):.2f} USDT)")
    targets = {t["symbol"]: t["weight"] * a.usdt for t in plan.get("targets", [])}
    for s, v in sorted(targets.items(), key=lambda kv: -kv[1]):
        print(f"  {s:12s} {'LONG ' if v > 0 else 'SHORT'} {abs(v):8.2f} USDT")
    key, sec = env()
    if not a.live or not key:
        print("\nโหมดทดลอง — ใส่ --live เพื่อส่งจริง (ถามยืนยันทุกออเดอร์)" + ("" if key else " · ยังไม่พบคีย์ใน carry.env")); return
    c = Client(key, sec)
    pos = {p["symbol"]: float(p["positionAmt"]) for p in c.signed("GET", FUT, "/fapi/v2/positionRisk", {}) if float(p["positionAmt"]) != 0}
    mine = set(json.loads(open("xs_symbols.json").read())) if __import__("os").path.exists("xs_symbols.json") else set()
    finfo = get(FUT + "/fapi/v1/exchangeInfo"); listed = {x["symbol"] for x in finfo["symbols"]}
    prices = {x["symbol"]: float(x["price"]) for x in get(FUT + "/fapi/v1/ticker/price")}
    orders = []
    fmap = {s: (s if s in listed else "1000" + s) for s in targets}
    pairs = [(s, fmap[s]) for s in targets] + [(fs, fs) for fs in sorted(mine & set(pos)) if fs not in fmap.values()]   # ปิดตัวที่หลุดแผน
    for s, fs in pairs:
        if fs not in listed: print(f"  ข้าม {s}: ไม่มีสัญญา perpetual"); continue
        cur = pos.get(fs, 0.0) * prices[fs]; want = targets.get(s, 0.0); diff = want - cur
        if abs(diff) < a.min: continue
        qstep, _ = filters(finfo, fs); qty = step(abs(diff) / prices[fs], qstep)
        if float(qty) <= 0: continue
        orders.append((s, fs, "BUY" if diff > 0 else "SELL", qty, diff, cur, want))
    if not orders:
        print("\nพอร์ตตรงกับแผนแล้ว — ไม่มีอะไรต้องทำ"); return
    for s, fs, side, qty, diff, cur, want in orders:
        print(f"\n[{fs}] ตอนนี้ {cur:+.2f} USDT → เป้าหมาย {want:+.2f} USDT : {side} {qty} (MARKET, ~{abs(diff):.2f} USDT)")
        if input("พิมพ์ yes เพื่อส่งออเดอร์นี้: ").strip().lower() != "yes": print("ข้าม"); continue
        try:
            if fs not in pos: c.signed("POST", FUT, "/fapi/v1/leverage", {"symbol": fs, "leverage": 1})
            o = c.signed("POST", FUT, "/fapi/v1/order", {"symbol": fs, "side": side, "type": "MARKET", "quantity": qty})
            print("ส่งแล้ว:", o.get("status"), "เติมแล้ว", o.get("executedQty")); mine.add(fs)
        except RuntimeError as e:
            print("Binance ปฏิเสธ:", e)
    open("xs_symbols.json", "w").write(json.dumps(sorted(mine)))   # จำว่าเหรียญไหนเปิดโดยกลยุทธ์นี้ (ไว้ปิดเมื่อหลุดแผน)


if __name__ == "__main__":
    main()
