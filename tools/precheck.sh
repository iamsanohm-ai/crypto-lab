#!/usr/bin/env bash
# ตรวจก่อน push ทุกครั้ง (ชุดเดียวกับ CI): ชุดทดสอบ + สร้างหน้าเว็บ/สรุปเช้า/รายงานสัปดาห์ + ไฟล์หน้าเว็บ
set -e
cd "$(dirname "$0")/.."
python -m pytest -q
python -c "from lab.brief import morning, weekly; assert len(morning()) > 200 and len(weekly()) > 100"
for f in docs/*.js; do node --check "$f"; done
echo "precheck OK"
