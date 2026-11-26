"""ยามเฝ้าระบบ: ตรวจว่าทุกส่วนยังทำงาน ถ้าผิดปกติส่ง Telegram ทันที.

python -m lab.watchdog            # ตรวจสุขภาพ (หน้าเว็บ/บอท/เทรดระยะสั้น/งาน GitHub ที่ล้มเหลว)
python -m lab.watchdog alert "ข้อความ"   # ส่งแจ้งเตือนตรงๆ (ใช้ใน workflow เมื่อขั้นตอนไหนพัง)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from lab.data import ROOT

STALE_MIN = {"หน้าเว็บ (data.json)": 45, "บอทหลัก": 45, "บอทระยะสั้น": 30}


def age_min(iso: str | None) -> float | None:
    if not iso:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 60


def send(text: str):
    from lab.notifier import Notifier
    Notifier(telegram=True).send("🚨 [Crypto Lab · ยามเฝ้าระบบ] " + text)


def failed_runs(window_min: int = 70) -> list[str]:
    repo, tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not tok:
        return []
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?per_page=30", headers={"Authorization": f"Bearer {tok}"})
    runs = json.loads(urllib.request.urlopen(req, timeout=20).read())["workflow_runs"]
    return [f"{r['name']} ล้มเหลว ({r['html_url']})" for r in runs
            if r["conclusion"] == "failure" and (age_min(r["updated_at"]) or 1e9) < window_min]


def check() -> list[str]:
    issues = []
    hb = ROOT / "docs" / "heartbeat.json"
    if hb.exists():
        h = json.loads(hb.read_text())
        for name, key in (("หน้าเว็บ (data.json)", "generated_at"), ("บอทหลัก", "last_bot_tick")):
            a = age_min(h.get(key))
            if a is None or a > STALE_MIN[name]:
                issues.append(f"{name} ไม่อัปเดตมา {a:.0f} นาที" if a else f"{name}: ไม่มีข้อมูลเวลา")
    sc = ROOT / "docs" / "scalper.json"
    if sc.exists():
        a = age_min(json.loads(sc.read_text()).get("updated_at"))
        if a is None or a > STALE_MIN["บอทระยะสั้น"]:
            issues.append(f"บอทระยะสั้นไม่อัปเดตมา {a:.0f} นาที" if a else "บอทระยะสั้น: ไม่มีข้อมูลเวลา")
    try:
        issues += failed_runs()
    except Exception as e:  # noqa: BLE001
        issues.append(f"ตรวจสถานะ GitHub ไม่ได้: {e}")
    return issues


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "alert":
        send(" ".join(sys.argv[2:])); return
    issues = check()
    if issues:
        send("พบปัญหา:\n• " + "\n• ".join(issues))
    print("OK" if not issues else "\n".join(issues))


if __name__ == "__main__":
    main()
