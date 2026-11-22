"""สร้างเอกสารสำหรับ store ของ dashboard (dash/meta, datasets/*, files/index.html) เป็นไฟล์ JSON
ใช้: python -m lab.dash_docs <blob_url> [--page]   → เขียนไฟล์ไว้ใน dashboard/docs/"""
from __future__ import annotations

import json
import sys

from lab.data import ROOT, now_iso

DOCS = ROOT / "dashboard" / "docs"
DATASETS = {
    "status": ("สถานะระบบ", "โหมด, ราคา BTC เทียบ EMA200 และเวลาที่บอทรันล่าสุด"),
    "candles": ("BTC/USDT แท่ง 4h", "แท่งเทียน 180 แท่งล่าสุดจาก Binance พร้อม EMA20, EMA200, RSI14"),
    "market": ("ราคาตลาด Top 20", "ราคาและการเปลี่ยนแปลง 24 ชม. ของเหรียญใน universe ของบอท จาก Binance"),
    "accounts": ("บัญชี paper ของแต่ละกลยุทธ์", "equity จำลอง และตัวเลข backtest ของ champion และ challengers"),
    "equity": ("Equity paper รายชั่วโมง", "equity ของแต่ละบัญชีทุกครั้งที่บอทรัน จาก ledger"),
    "positions": ("สถานะที่ถืออยู่", "สถานะ paper ที่เปิดอยู่ พร้อม stop"),
    "risk": ("Sentinel ความเสี่ยง", "ขาดทุนวันนี้, แพ้ติดกัน และสถานะหยุดของแต่ละบัญชี"),
    "events": ("สัญญาณและการตัดสินใจ", "40 เหตุการณ์ล่าสุดจาก ledger: ซื้อ ขาย สัญญาณ และการตัดสินใจของ Sentinel"),
    "leaderboard": ("อันดับกลยุทธ์ (backtest)", "ผล walk-forward หลังต้นทุนของทุกไอเดีย และเกณฑ์เทียบ"),
    "bt_curves": ("Equity backtest รายวัน", "เส้น equity walk-forward ของกลยุทธ์ที่เลือก เทียบ BTC buy & hold เริ่ม 500 USDT"),
}


def main(url: str, page: bool):
    DOCS.mkdir(parents=True, exist_ok=True)
    stamp = {"at": now_iso(), "by": "Crypto Lab bot"}
    for k, (title, desc) in DATASETS.items():
        doc = {"title": title, "description": desc,
               "source": {"kind": "file", "url": url, "name": "data.json", "format": "json"},
               "updated": stamp, "schedule": "บอทอัปเดตทุกชั่วโมง", "staleAfterHours": 3}
        (DOCS / f"dataset_{k}.json").write_text(json.dumps(doc, ensure_ascii=False))
    if page:
        (DOCS / "meta.json").write_text(json.dumps({"title": "Crypto Lab Terminal", "lang": "th"}, ensure_ascii=False))
        (DOCS / "index.json").write_text(json.dumps({"text": (ROOT / "dashboard" / "index.html").read_text()}, ensure_ascii=False))
    print("ok", len(DATASETS), "datasets", "+ page" if page else "")


if __name__ == "__main__":
    main(sys.argv[1], "--page" in sys.argv)
