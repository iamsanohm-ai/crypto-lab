"""ตัวส่งออเดอร์ "เก็บ funding" — รันบนคอมของเจ้าของเท่านั้น (เซิร์ฟเวอร์ GitHub ถูก Binance บล็อก)

ทำอะไร: ดู funding สดของ Top 20 → ตามกฎที่ทดสอบแล้ว (เข้า: funding เฉลี่ย 3 วัน > 0.01%/รอบ, สูงสุด 5 เหรียญ; ออก: เฉลี่ย ≤ 0)
        → เสนอแผน "ซื้อ spot + short perpetual เท่ากัน" หรือ "ปิดทั้งสองขา" → ถามคุณทีละออเดอร์ (ต้องพิมพ์ yes) → ส่งเป็น limit/maker

ความปลอดภัย:
  • ค่าเริ่มต้น = โหมดทดลอง (ไม่ส่งอะไรเลย แค่แสดงแผน) · ต้องใส่ --live เพื่อส่งจริง และยังต้องพิมพ์ yes ทุกออเดอร์
  • คีย์อ่านจากตัวแปรแวดล้อม BINANCE_API_KEY / BINANCE_API_SECRET หรือไฟล์ carry.env ข้างสคริปต์ (ห้าม commit / ห้ามส่งในแชต)
  • สร้างคีย์ที่เปิดเฉพาะ "Enable Spot & Margin Trading" + "Enable Futures" · ปิด Withdrawals · จำกัด IP เป็นเครื่องนี้
  • leverage futures ตั้งเป็น 1x · จำนวนเงินต่อเหรียญจำกัดด้วย --usdt (ค่าเริ่มต้น 20)
  • limit แบบ maker อาจจับคู่ไม่ครบ → สคริปต์รอ แล้วรายงานถ้าสองขาไม่เท่ากัน (ให้คุณตัดสินใจเองว่าจะเติม/ยกเลิก)

ใช้งาน (Windows: เปิด Command Prompt ในโฟลเดอร์นี้):
  python carry_executor.py                 # ดูแผนอย่างเดียว
  python carry_executor.py --live --usdt 20
ต้องการแค่ Python 3.10+ (ไม่ต้องติดตั้งอะไรเพิ่ม)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

SPOT, FUT = "https://api.binance.com", "https://fapi.binance.com"
PAGES = "https://iamsanohm-ai.github.io/crypto-lab/data.json"
ENTER, EXIT, MAXC = 0.0001, 0.0, 5


def env():
    f = Path(__file__).with_name("carry.env")
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    return os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_API_SECRET")


def get(url, params=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    with urllib.request.urlopen(url + q, timeout=20) as r:
        return json.loads(r.read())


class Client:
    def __init__(self, key, secret):
        self.key, self.secret = key, secret.encode()

    def signed(self, method, base, path, params):
        params = dict(params, timestamp=int(time.time() * 1000), recvWindow=5000)
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(self.secret, qs.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(f"{base}{path}?{qs}&signature={sig}", method=method, headers={"X-MBX-APIKEY": self.key})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{path}: {e.code} {e.read().decode()[:300]}") from None


def step(x: float, s: str) -> str:
    d = Decimal(s).normalize()
    return format((Decimal(str(x)) / d).to_integral_value(rounding=ROUND_DOWN) * d, "f")


def filters(info, sym):
    f = {x["filterType"]: x for x in next(s for s in info["symbols"] if s["symbol"] == sym)["filters"]}
    return f["LOT_SIZE"]["stepSize"], f["PRICE_FILTER"]["tickSize"]


def plan(usdt):
    top = [m["symbol"] + "USDT" for m in get(PAGES)["market"]]
    prem = {p["symbol"]: p for p in get(FUT + "/fapi/v1/premiumIndex")}
    rates = {}
    for s in top:
        fs = s if s in prem else "1000" + s
        if fs not in prem: continue
        h = get(FUT + "/fapi/v1/fundingRate", {"symbol": fs, "limit": 9})
        rates[s] = {"fut": fs, "avg": sum(float(x["fundingRate"]) for x in h) / max(1, len(h)), "last": float(prem[fs]["lastFundingRate"])}
    want = [s for s, r in sorted(rates.items(), key=lambda kv: -kv[1]["avg"]) if r["avg"] > ENTER][:MAXC]
    print("\nfunding เฉลี่ย 3 วัน (ต่อรอบ 8 ชม.):")
    for s, r in sorted(rates.items(), key=lambda kv: -kv[1]["avg"]):
        print(f"  {s:12s} {r['avg'] * 100:+.4f}%  (~{r['avg'] * 3 * 365 * 100:+.1f}%/ปี)  {'← เข้าเกณฑ์' if s in want else ''}")
    return rates, want


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); ap.add_argument("--usdt", type=float, default=20.0)
    a = ap.parse_args()
    rates, want = plan(a.usdt)
    key, sec = env()
    if not a.live or not key:
        print(f"\nโหมดทดลอง: แผนคือถือ {want or 'ไม่มี'} เหรียญละ {a.usdt} USDT ต่อขา" + ("" if key else " (ยังไม่พบคีย์ — ใส่ใน carry.env)"))
        print("ใส่ --live เพื่อส่งออเดอร์จริง (ระบบจะถามยืนยันทุกออเดอร์)"); return
    c = Client(key, sec)
    held = {p["symbol"]: float(p["positionAmt"]) for p in c.signed("GET", FUT, "/fapi/v2/positionRisk", {}) if float(p["positionAmt"]) < 0}
    sinfo, finfo = get(SPOT + "/api/v3/exchangeInfo"), get(FUT + "/fapi/v1/exchangeInfo")
    actions = [("open", s) for s in want if rates[s]["fut"] not in held]
    actions += [("close", s) for s, r in rates.items() if r["fut"] in held and r["avg"] <= EXIT]
    if not actions:
        print("\nไม่มีอะไรต้องทำตอนนี้ (ถืออยู่: " + (", ".join(held) or "ไม่มี") + ")"); return
    for kind, s in actions:
      try:
        fs = rates[s]["fut"]
        sb = get(SPOT + "/api/v3/ticker/bookTicker", {"symbol": s}); fb = get(FUT + "/fapi/v1/ticker/bookTicker", {"symbol": fs})
        sstep, stick = filters(sinfo, s); fstep, ftick = filters(finfo, fs)
        if kind == "open":
            mult = 1000 if fs.startswith("1000") else 1
            qty_f = step(a.usdt / float(fb["askPrice"]), fstep); qty_s = step(float(qty_f) * mult, sstep)
            print(f"\n[{s}] เปิด: ซื้อ spot {qty_s} @ {sb['bidPrice']} (limit maker) + short {fs} {qty_f} @ {fb['askPrice']} (limit post-only, 1x)")
            if input("พิมพ์ yes เพื่อส่งทั้งสองขา: ").strip().lower() != "yes": print("ข้าม"); continue
            c.signed("POST", FUT, "/fapi/v1/leverage", {"symbol": fs, "leverage": 1})
            o2 = c.signed("POST", FUT, "/fapi/v1/order", {"symbol": fs, "side": "SELL", "type": "LIMIT", "timeInForce": "GTX", "quantity": qty_f, "price": step(float(fb["askPrice"]), ftick)})
            try:   # ส่งขา futures ก่อน (มักโดนปฏิเสธเพราะขั้นต่ำ) แล้วค่อย spot — ถ้า spot ไม่ผ่าน ยกเลิกขา futures ที่ยังไม่จับคู่ เพื่อไม่ให้เหลือขาเดียว
                o1 = c.signed("POST", SPOT, "/api/v3/order", {"symbol": s, "side": "BUY", "type": "LIMIT_MAKER", "quantity": qty_s, "price": step(float(sb["bidPrice"]), stick)})
            except RuntimeError as e:
                c.signed("DELETE", FUT, "/fapi/v1/order", {"symbol": fs, "orderId": o2["orderId"]}); print("spot ไม่ผ่าน → ยกเลิกขา futures แล้ว:", e); continue
        else:
            amt = abs(held[fs]); bal = next((float(b["free"]) for b in c.signed("GET", SPOT, "/api/v3/account", {})["balances"] if b["asset"] == s[:-4]), 0.0)
            print(f"\n[{s}] ปิด (funding เฉลี่ยไม่เป็นบวกแล้ว): ขาย spot {step(bal, sstep)} + ปิด short {fs} {amt}")
            if input("พิมพ์ yes เพื่อส่งทั้งสองขา: ").strip().lower() != "yes": print("ข้าม"); continue
            o2 = c.signed("POST", FUT, "/fapi/v1/order", {"symbol": fs, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "reduceOnly": "true", "quantity": step(amt, fstep), "price": step(float(fb["bidPrice"]), ftick)})
            try:
                o1 = c.signed("POST", SPOT, "/api/v3/order", {"symbol": s, "side": "SELL", "type": "LIMIT_MAKER", "quantity": step(bal, sstep), "price": step(float(sb["askPrice"]), stick)})
            except RuntimeError as e:
                c.signed("DELETE", FUT, "/fapi/v1/order", {"symbol": fs, "orderId": o2["orderId"]}); print("spot ไม่ผ่าน → ยกเลิกขา futures แล้ว:", e); continue
        print("ส่งแล้ว — spot:", o1.get("status"), "| futures:", o2.get("status"), "· รอ 60 วินาทีแล้วตรวจว่าจับคู่ครบไหม")
        time.sleep(60)
        s1 = c.signed("GET", SPOT, "/api/v3/order", {"symbol": s, "orderId": o1["orderId"]}); s2 = c.signed("GET", FUT, "/fapi/v1/order", {"symbol": fs, "orderId": o2["orderId"]})
        print(f"spot เติมแล้ว {s1['executedQty']}/{s1['origQty']} · futures เติมแล้ว {s2['executedQty']}/{s2['origQty']}")
        if s1["status"] != "FILLED" or s2["status"] != "FILLED":
            print("⚠️ สองขายังไม่เท่ากัน — เปิดแอป Binance เพื่อยกเลิกส่วนที่ค้าง หรือเติมขาที่ขาด (สคริปต์จะไม่ทำเองโดยไม่ถาม)")
      except RuntimeError as e:
        print(f"[{s}] Binance ปฏิเสธ: {e} — ข้ามเหรียญนี้ (ตรวจในแอป Binance ว่าไม่มีออเดอร์ค้าง)")

if __name__ == "__main__":
    main()
