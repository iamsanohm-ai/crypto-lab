"""Grok (xAI) เป็น "ผู้ตรวจสอบ" สัญญาณซื้อ — อนุญาตหรือคัดค้านได้อย่างเดียว ไม่สามารถสั่งซื้อหรือเพิ่มขนาดไม้เอง.

โหมด (config/strategy.yaml → grok.mode):
  shadow : ถาม Grok และบันทึกความเห็นลง ledger แต่ไม่มีผลกับการเทรด (ใช้วัดว่ามีประโยชน์จริงไหม)
  veto   : ถ้า Grok คัดค้าน บอทจะข้ามการซื้อนั้น
ถ้าเรียก Grok ไม่สำเร็จ / ตอบผิดรูปแบบ / เกินโควตา → ถือว่า "allow" (Sentinel ยังคุมความเสี่ยงอยู่เสมอ)
ต้องมี env XAI_API_KEY (ใส่ใน GitHub Secrets เท่านั้น)
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from lab.data import ROOT

API_URL = "https://api.x.ai/v1/chat/completions"
USAGE = ROOT / "state" / "grok_usage.json"

SYSTEM = (
    "You are a risk reviewer for a small, rules-based, long-only crypto spot paper-trading bot. "
    "A backtested strategy proposes a BUY. You may only ALLOW or VETO it; you cannot propose trades or change size. "
    "VETO only for a concrete, current reason the rules cannot see (e.g. exchange hack, delisting notice, regulatory "
    "action, token unlock, major scheduled macro event within hours). Do not veto for generic bearishness. "
    "Use only the facts given plus events you are confident about; if unsure, ALLOW. "
    'Reply with JSON only: {"decision": "allow" | "veto", "confidence": 0-1, "reason": "<one sentence>"}'
)


def _usage_ok(limit: int) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    u = json.loads(USAGE.read_text()) if USAGE.exists() else {}
    if u.get("day") != today:
        u = {"day": today, "calls": 0}
    if u["calls"] >= limit:
        return False
    u["calls"] += 1
    USAGE.parent.mkdir(exist_ok=True)
    USAGE.write_text(json.dumps(u))
    return True


def parse(text: str) -> dict:
    """ดึง JSON จากคำตอบ; อะไรที่ไม่ใช่รูปแบบที่กำหนด → allow."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        d = json.loads(text[start:end])
        dec = str(d.get("decision", "")).lower()
        if dec not in ("allow", "veto"):
            raise ValueError
        conf = float(d.get("confidence", 0))
        return {"decision": dec, "confidence": max(0.0, min(1.0, conf)), "reason": str(d.get("reason", ""))[:300]}
    except Exception:
        return {"decision": "allow", "confidence": 0.0, "reason": "unparseable reply → default allow"}


def review(cfg: dict, signal: dict, post=None) -> dict | None:
    """คืนความเห็นของ Grok หรือ None ถ้าปิดอยู่ / ไม่มีคีย์ / เกินโควตา."""
    g = (cfg or {}).get("grok") or {}
    key = os.environ.get("XAI_API_KEY")
    if not g.get("enabled") or not key or not _usage_ok(int(g.get("max_calls_per_day", 20))):
        return None
    body = {"model": g.get("model", "grok-4"), "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps(signal, default=str)}]}
    try:
        if post is None:
            req = urllib.request.Request(API_URL, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = json.loads(r.read())["choices"][0]["message"]["content"]
        else:
            text = post(body)
    except Exception as e:
        return {"decision": "allow", "confidence": 0.0, "reason": f"Grok error → default allow: {e}"[:300], "error": True}
    res = parse(text)
    # veto ที่ความมั่นใจต่ำไม่นับ
    if res["decision"] == "veto" and res["confidence"] < float(g.get("min_veto_confidence", 0.6)):
        res["decision"], res["reason"] = "allow", f"(low-confidence veto ignored) {res['reason']}"
    return res
