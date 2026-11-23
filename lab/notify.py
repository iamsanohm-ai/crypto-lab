"""ส่ง morning brief / weekly review ทาง Telegram (ฟรี) ถ้าตั้ง TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID ไว้ใน GitHub Secrets
และบันทึกเป็นไฟล์ research/brief/ เสมอ."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from lab.brief import morning, weekly
from lab.data import ROOT
from lab.notifier import Notifier


def main():
    kind = "weekly" if "weekly" in sys.argv else "morning"
    text = weekly() if kind == "weekly" else morning()
    d = ROOT / "research" / "brief"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{datetime.now(timezone.utc):%Y-%m-%d}_{kind}.md").write_text(text)
    (d / f"latest_{kind}.md").write_text(text)
    Notifier(telegram=True).send(text[:4000])


if __name__ == "__main__":
    main()
