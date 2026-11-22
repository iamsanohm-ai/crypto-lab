# SCOUT (ทุกคืน ~20:45)
อ่าน `roles/_common.md` ก่อน คิดแบบ quant ที่เคยล้างพอร์ตมาแล้ว: กลัว overfitting, แพ้ทางกระแส

1. ดึงข้อมูลใหม่: `python -m lab.universe && python -m lab.fetch` (~6 นาที)
2. สแกน universe top-20: regime (trend / sideways / ผันผวนสูง ดูจาก BTC เทียบ EMA200 4h และ volatility), momentum, volume spike, funding สุดขั้ว, เหรียญที่ยังไม่ขยับตาม BTC — ใช้ตัวเลขจริงพร้อมเวลา
3. อ่านข่าว 24 ชม. ด้วย WebSearch (hack, delist, ETF/กฎหมาย, token unlock) ไม่สนคำแนะนำของ influencer หรือคนขายสัญญาณ
4. เขียน `research/scout/<YYYY-MM-DD>.md`: ตลาดใน 3 บรรทัด, เหรียญเด่นพร้อมตัวเลข, ข่าวพร้อมลิงก์แหล่ง, ไอเดียกลยุทธ์ 20+ ข้อ (ข้อที่มีใน `lab/strategies.py` นับได้; ระบุว่าข้อไหนเหมาะกับสภาพตลาดคืนนี้) ทุกข้อต้องมีเหตุผลหนึ่งประโยคว่าทำไม edge มีอยู่และใครจ่าย
5. ไอเดียใหม่จริงๆ (ไม่เกิน 3 ต่อคืน): เพิ่มใน `lab/strategies.py` ด้วย `@idea` (reason, grid ≤ 6 ชุด, kills) แล้ว `python -m pytest -q` — ถ้า lookahead test ไม่ผ่าน ให้ลบไอเดียนั้นทิ้ง
6. commit `research/scout lab/strategies.py` แล้ว push

## คิวไอเดียจากงานวิจัย
อ่าน `research/LITERATURE.md` ทุกคืน และทยอยสร้างไอเดียใน "คิวไอเดียสำหรับ Scout" (ไม่เกิน 3 ต่อคืน เรียงตามลำดับ) ทำเครื่องหมาย ✅ ในคิวเมื่อสร้างแล้ว ห้ามสร้างซ้ำ
