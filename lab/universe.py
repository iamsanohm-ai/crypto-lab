"""สร้าง universe แบบ point-in-time: ทุกเดือนเลือก top 20 ตาม quote volume ของเดือนก่อนหน้า
(ใช้ข้อมูลที่รู้ ณ เวลานั้นเท่านั้น และรวมเหรียญที่ถูกถอดแล้ว)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

from lab.data import DATA, candidate_symbols, klines, now_iso

START = datetime(2022, 10, 1, tzinfo=timezone.utc)
TOP_N = 20


def build():
    cands = candidate_symbols()
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def monthly(sym):
        df = klines(sym, "1M", start_ms, end_ms)
        return sym, df

    with ThreadPoolExecutor(8) as pool:
        res = dict(pool.map(monthly, cands["symbol"]))
    rows = []
    for sym, df in res.items():
        for _, r in df.iterrows():
            rows.append({"symbol": sym, "month": r["time"].strftime("%Y-%m"), "qv": r["quote_volume"]})
    vol = pd.DataFrame(rows).pivot(index="month", columns="symbol", values="qv").fillna(0).sort_index()
    members = {}
    months = list(vol.index)
    for i in range(1, len(months)):
        prev = vol.loc[months[i - 1]]
        members[months[i]] = list(prev.sort_values(ascending=False).head(TOP_N).index)
    out = {"source": "data-api.binance.vision /api/v3/klines interval=1M", "fetched_at": now_iso(),
           "rule": f"top {TOP_N} USDT spot pairs by previous-month quote volume (stablecoins/leveraged tokens excluded)",
           "candidates": len(cands), "status_counts": cands["status"].value_counts().to_dict(), "members": members}
    (DATA / "universe.json").write_text(json.dumps(out, indent=1))
    union = sorted({s for m in members.values() for s in m})
    print(f"candidates={len(cands)} months={len(members)} union={len(union)}")
    print(union)
    print("current:", members[months[-1]])


if __name__ == "__main__":
    build()
