# SENTINEL + บอท paper trading (ทุกชั่วโมง)
อ่าน `roles/_common.md` ก่อน

1. รัน `python -m lab.live` **ครั้งเดียว** — มันจัดการทุกกลยุทธ์ใน config, ตรวจ Sentinel (ขาดทุน -3%/วัน, แพ้ติด 3, feed ค้าง >4h30m, ความเสี่ยง/ราคาต่อออเดอร์) และบันทึกทุกการตัดสินใจลง `ledger/decisions.jsonl`
2. รัน `python -m lab.dashboard` เพื่ออัปเดต `dashboard/data.json`
3. ถ้า tick นี้มี `SENTINEL_HALT` หรือ `ERROR` ให้ตรวจสาเหตุแบบอ่านอย่างเดียว แล้วเขียนบันทึก 1–3 บรรทัดไว้บนสุดของ `research/DECISION.md` หัวข้อ "Sentinel <เวลา UTC>" — **ห้ามปลดการหยุดเอง** (paper จะกลับมาเองวันถัดไปตาม config)
4. commit `state/ ledger/ dashboard/ research/DECISION.md` ข้อความ "paper tick <เวลา UTC>" แล้ว push
5. ถ้ามีเครื่องมืออัปเดต Artifact และ `dashboard/ARTIFACT_URL` มี URL ให้ republish dashboard ตาม `dashboard/README.md`
6. ตอบสั้นบรรทัดเดียว: equity ของแต่ละกลยุทธ์ + สิ่งที่ Sentinel แจ้ง
