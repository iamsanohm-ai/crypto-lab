# Crypto Lab 🧪

ห้องวิจัยกลยุทธ์คริปโต + บอท paper trading (Binance spot, 4h, top-20 USDT) ทำงานตามตารางบน cloud

## โครงสร้าง
| path | หน้าที่ |
|---|---|
| `lab/data.py`, `lab/universe.py`, `lab/fetch.py` | ดึงข้อมูลจริง 4 ปี (บันทึกแหล่ง+เวลาใน `data/manifest.json`), universe แบบ point-in-time รวมเหรียญที่ถูกถอด |
| `lab/strategies.py` | **Scout** — 22 ไอเดีย แต่ละข้อมีเหตุผลว่าทำไม edge มีอยู่ |
| `lab/engine.py`, `lab/judge.py`, `lab/final_check.py` | **Judge** — backtest walk-forward หลังต้นทุน, ให้คะแนน, final check |
| `lab/live.py` | บอท paper trading + **Sentinel** (รันทุกชั่วโมง) |
| `lab/brief.py` | morning brief / weekly review |
| `config/strategy.yaml` | สลับกลยุทธ์ + กติกาความเสี่ยง ในไฟล์เดียว |
| `research/` | `SUMMARY.md`, strategy cards, ผล JSON |
| `ledger/decisions.jsonl` | บันทึกทุกการตัดสินใจของบอทพร้อมเหตุผล (append-only) |
| `state/` | สถานะบัญชีจำลองของแต่ละกลยุทธ์ |
| `cryptoassist/` | CLI ตัวแรก (ดูราคา/แจ้งเตือน/พอร์ต) |

## คำสั่ง
```bash
pip install -r requirements.txt
python -m lab.universe && python -m lab.fetch   # ดึงข้อมูล (~6 นาที)
python -m lab.judge                             # backtest ทุกไอเดีย (~1 นาที)
python -m lab.final_check keltner_trend golden_cross_50_200
python -m lab.cards                             # เขียน strategy cards
python -m lab.live                              # paper trade 1 รอบ
python -m lab.brief                             # morning brief
python -m pytest -q
```

## กติกาที่ห้ามละเมิด
- Paper เท่านั้นจนกว่าเจ้าของจะพิมพ์ "go live"; เงินจริงต้องอนุมัติทุกเทรด
- API key: trade-only, ปิดถอนเงิน, เก็บใน environment เท่านั้น ห้ามอยู่ในโค้ดหรือแชต
- ห้ามแต่งตัวเลข — ทุกราคา/ผลลัพธ์มาจากข้อมูลจริงที่มีแหล่งและเวลา ค่าประมาณต้องติดป้าย (เช่น funding live = ESTIMATE)
- Sentinel หยุดทุกอย่างเมื่อ: ขาดทุน -3%/วัน, แพ้ติด 3, feed ค้าง

## ระบบอัตโนมัติ (ฟรี ไม่ใช้ AI)
| งาน | ที่รัน | เวลา (ไทย) |
|---|---|---|
| บอท paper + Sentinel | GitHub Actions `paper-bot.yml` | ทุกชั่วโมง (GitHub อาจเลื่อนเวลา) |
| Judge: ดึงข้อมูล + backtest + final check + cards | `nightly.yml` | 22:43 |
| Morning brief (+ บอทรันอีกรอบ) | `nightly.yml` | 07:05 |
| Weekly review | `nightly.yml` | อาทิตย์ 09:35 |

แจ้งเตือนทาง Telegram (ฟรี): ใส่ `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` ใน GitHub → Settings → Secrets and variables → Actions
รันเองทันที: GitHub → Actions → เลือก workflow → Run workflow
งานที่ต้องใช้ AI (คิดไอเดียใหม่, อ่านข่าว, แก้บั๊ก) ทำเมื่อเจ้าของสั่งเท่านั้น — `roles/*.md` คือคู่มือ
