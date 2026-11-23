"""ส่งการแจ้งเตือน: แสดงใน terminal เสมอ + Telegram ถ้าเปิดใช้."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime

from rich.console import Console

console = Console()


class Notifier:
    def __init__(self, telegram: bool = False):
        self.tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") if telegram else None
        self.tg_chat = os.environ.get("TELEGRAM_CHAT_ID") if telegram else None
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        self.sent.append(message)
        console.print(f"[bold magenta]🔔 {datetime.now():%H:%M:%S}[/] {message}")
        if self.tg_token and self.tg_chat:
            try:
                data = json.dumps({"chat_id": self.tg_chat, "text": message}).encode()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:  # ไม่ให้แจ้งเตือนพังแล้วบอทหยุด
                console.print(f"[red]ส่ง Telegram ไม่สำเร็จ: {e}[/]")
