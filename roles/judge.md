# JUDGE (ทุกคืน ~22:45)
อ่าน `roles/_common.md` ก่อน เลือกสิ่งที่น่าเบื่อแต่พิสูจน์แล้ว มากกว่าสิ่งที่น่าตื่นเต้นแต่โชคดี

1. `python -m lab.universe && python -m lab.fetch` แล้ว `python -m pytest -q` ต้องผ่าน
2. `python -m lab.judge` — walk-forward ทุกไอเดียหลังต้นทุน
3. ตัวที่รอด (กำไรหลังต้นทุน และ Sharpe > BTC buy & hold) → `python -m lab.final_check <ชื่อ...>` (ค่าธรรมเนียม×2, ±20% พารามิเตอร์, ≥50 เทรด, รายช่วง) และเช็คการกระจุกของกำไร (ตัด 5 เทรดที่ดีที่สุด / ตัดเหรียญที่ดีที่สุด จาก `data/wf_trades_<ชื่อ>.parquet`)
4. `python -m lab.cards` อัปเดต SUMMARY และ cards (ทุก card จบด้วย WHY THIS COULD FAIL)
5. เทียบผล paper (`state/`, `ledger/`) กับความคาดหวังจาก backtest — edge ไหนจางลง
6. ถ้ามีกลยุทธ์ใหม่ชนะ champion/challenger ทุก final check หรือ challenger ชนะ champion บน paper ≥7 วัน ≥5 เทรด → เขียน**ข้อเสนอ**พร้อมตัวเลขใน `research/DECISION.md`
7. commit `research/` แล้ว push

## Deflated Sharpe
ถ้ายังไม่มี ให้เพิ่ม Deflated Sharpe Ratio (Bailey & López de Prado) ใน `lab/final_check.py` โดยใช้จำนวนไอเดียทั้งหมดที่ทดสอบเป็น N trials และรายงานค่าใน cards — ตัวที่ DSR < 0.5 ให้ระบุว่า "อาจเป็นโชค"
