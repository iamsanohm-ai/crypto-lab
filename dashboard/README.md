# Dashboard

**หลัก (ฟรี):** GitHub Pages จากโฟลเดอร์ `docs/` → https://iamsanohm-ai.github.io/crypto-lab/
- `docs/index.html` + `docs/app.js` + `docs/d3.min.js` อ่าน `docs/data.json`
- `python -m lab.dashboard` เขียน `dashboard/data.json` และ `docs/data.json` (GitHub Actions รันทุกชั่วโมง แล้ว commit → Pages อัปเดตเอง)

**สำรอง:** Artifact บน claude.ai (`dashboard/ARTIFACT_URL`, ต้นฉบับ `dashboard/index.html`) อัปเดตได้เฉพาะเมื่อสั่ง AI (ขั้นตอนเดิมด้านล่าง)
1. `python -m lab.dashboard` 2. `Artifact` read ARTIFACT_URL 3. publish `asset: true` file `dashboard/data.json`
4. `python -m lab.dash_docs /_blob/<id>` 5. `ArtifactData` batch update `datasets/*` (pin `if_version`) 6. ลบ asset เก่าตาม `dashboard/BLOB_URL`
