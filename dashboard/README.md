# Dashboard: Crypto Lab Terminal

Artifact: ดู `dashboard/ARTIFACT_URL` (ชนิด "Data") · หน้าเว็บอยู่ที่ `dashboard/index.html` (ต้นฉบับ) และใน store ของ artifact (`files/index.html`)
ข้อมูลทั้งหมดมาจากไฟล์เดียว `dashboard/data.json` ที่ `python -m lab.dashboard` สร้าง (ข้อมูลจริงจาก Binance + state/ledger/research)

## อัปเดตข้อมูลทุกชั่วโมง (ทำโดย Sentinel หลัง `lab.live`)
1. `python -m lab.dashboard`
2. `Artifact` action `read` url = ARTIFACT_URL (ครั้งแรกใน session — จำเป็นก่อนเขียน)
3. `Artifact` publish: `url` = ARTIFACT_URL, `file_path` = `dashboard/data.json`, `asset: true` → ได้ `/_blob/<id>` ใหม่
4. `python -m lab.dash_docs /_blob/<id>` → สร้าง `dashboard/docs/dataset_*.json`
5. `ArtifactData` action `list` collection `datasets` เพื่อดู `version` ของแต่ละ dataset แล้ว `ArtifactData` action `batch` ด้วย `op: "update"`, `collection: "datasets"`, `doc_id` = ชื่อ, `file_path` = `dashboard/docs/dataset_<ชื่อ>.json`, `if_version` = version ที่อ่านได้ (ทั้ง 10 ตัวใน batch เดียว)
6. ลบไฟล์เก่า: `Artifact` action `delete` url = ARTIFACT_URL, `path` = id ของไฟล์เก่า (จาก `dashboard/BLOB_URL`) แล้วเขียน `/_blob/<id>` ใหม่ลง `dashboard/BLOB_URL`
7. ห้ามแก้หน้าเว็บ (`files/index.html`) ในขั้นนี้ — เปลี่ยนหน้าเว็บทำโดย Engineer เมื่อเจ้าของขอเท่านั้น

ถ้าไม่มีเครื่องมือ Artifact/ArtifactData ใน session ให้ข้ามขั้น 2–6 และบอกในคำตอบว่า dashboard ไม่ได้อัปเดต (ข้อมูลยังอยู่ใน `dashboard/data.json` ใน repo)
