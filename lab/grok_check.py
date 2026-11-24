"""ตรวจว่า XAI_API_KEY ใช้ได้ และบัญชีใช้รุ่นไหนได้บ้าง (พิมพ์เฉพาะชื่อรุ่น ไม่พิมพ์คีย์) แล้วลองเรียก review 1 ครั้งแบบตัวอย่าง."""
import json
import os
import urllib.request

import yaml

from lab import grok
from lab.data import ROOT

key = os.environ.get("XAI_API_KEY")
print("key set:", bool(key))
req = urllib.request.Request("https://api.x.ai/v1/models", headers={"Authorization": f"Bearer {key}"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("models:", [m["id"] for m in json.loads(r.read()).get("data", [])])
except urllib.error.HTTPError as e:
    print("models error:", e.code, e.read().decode(errors="replace")[:400])
except Exception as e:
    print("models error:", e)
print("key looks like xai-...:", bool(key) and key.strip().startswith("xai-"), "| has whitespace/newline:", bool(key) and key != key.strip())
cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
cfg["grok"]["enabled"] = True
res = grok.review(cfg, {"symbol": "TESTUSDT", "note": "connectivity test only, not a real signal", "price_now": 1.0})
print("configured model:", cfg["grok"]["model"], "| test review:", res)
