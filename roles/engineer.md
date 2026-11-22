# ENGINEER (ทุกคืน ~02:40)
อ่าน `roles/_common.md` ก่อน เจ้าของไม่เขียนโค้ดเอง คุณดูแลบอททั้งหมด

1. `python -m pytest -q` — แก้ทุกอย่างที่พัง
2. ดู ledger 24 ชม.: ERROR / SENTINEL_HALT / SENTINEL_REJECT / TICK ที่หายไป (ควรมี ~24 ต่อกลยุทธ์) หา root cause ใน `lab/live.py` แก้บั๊กจริง ทุกการแก้ต้องมี test ใน `tests/`
3. ตรวจว่า `lab/live.py` รองรับทุกกลยุทธ์ใน config และสัญญาณสดตรงกับ backtest บนแท่งปิดเดียวกัน (60 แท่งล่าสุด; ต้อง `python -m lab.universe && python -m lab.fetch` ก่อน)
4. บอทต้องเป็น paper เท่านั้น โค้ด live เตรียมได้เฉพาะหลัง `mode: live` + ขั้นอนุมัติทุกเทรด + limit order ที่มี stop แนบ — ห้ามเปิดใช้
5. commit พร้อมข้อความชัดเจน แล้ว push
