# DASHBOARD REFRESH (ทุก 4 ชั่วโมง)
อ่าน `roles/_common.md` ก่อน

บอทและ Sentinel รันเองทุกชั่วโมงบน GitHub Actions (`.github/workflows/paper-bot.yml`) โดยไม่ใช้ AI
งานของคุณมีแค่:
1. `git pull --rebase origin main` (ได้ state/ledger และ `dashboard/data.json` ล่าสุดจาก Actions)
2. ตรวจว่า Actions ยังทำงาน: ดูเวลาของ TICK ล่าสุดใน `ledger/decisions.jsonl` ถ้าเก่ากว่า 3 ชั่วโมง ให้เขียนบันทึกบนสุดของ `research/DECISION.md` ("บอทหยุดรันตั้งแต่ <เวลา>") แล้วรัน `python -m lab.live` เองหนึ่งครั้ง
3. `python -m lab.dashboard` แล้วอัปเดต dashboard ตาม `dashboard/README.md` ขั้น 2–6
4. ถ้าใน 4 ชั่วโมงที่ผ่านมามี SENTINEL_HALT หรือ ERROR ให้สรุปสาเหตุ 1–3 บรรทัดบนสุดของ `research/DECISION.md` (ห้ามปลดการหยุดเอง)
5. commit `dashboard/BLOB_URL research/DECISION.md` (และ state/ledger ถ้ารันเองในขั้น 2) แล้ว push
6. ตอบสั้นบรรทัดเดียวเป็นภาษาไทย
