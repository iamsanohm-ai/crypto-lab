"""ดาวน์โหลดแท่ง 4h + funding ของทุกเหรียญที่เคยอยู่ใน universe."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

from lab.data import DATA, funding, klines, now_iso
from lab.universe import START


def months_between(a: datetime, b: datetime) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(a.strftime("%Y-%m"), b.strftime("%Y-%m"), freq="M")]


def main():
    uni = json.loads((DATA / "universe.json").read_text())
    syms = sorted({s for m in uni["members"].values() for s in m})
    start_ms = int(START.timestamp() * 1000)
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    months = months_between(START, now)
    manifest = {}

    def one(sym):
        k = klines(sym, "4h", start_ms, end_ms)
        if not k.empty:
            k = k[k["close_time"] < end_ms]  # ตัดแท่งที่ยังไม่ปิด
            k.drop(columns="close_time").to_parquet(DATA / "klines" / f"{sym}.parquet")
        f = funding(sym, months)
        if not f.empty:
            f.to_parquet(DATA / "funding" / f"{sym}.parquet")
        return sym, {"bars": len(k), "first": str(k["time"].min()) if len(k) else None,
                     "last": str(k["time"].max()) if len(k) else None, "funding_rows": len(f)}

    with ThreadPoolExecutor(6) as pool:
        for sym, info in pool.map(one, syms):
            manifest[sym] = info
    json.dump({"fetched_at": now_iso(), "sources": {
        "klines": "https://data-api.binance.vision/api/v3/klines interval=4h",
        "funding": "https://data.binance.vision/data/futures/um/monthly/fundingRate"}, "symbols": manifest},
        open(DATA / "manifest.json", "w"), indent=1)
    print(len(manifest), "symbols;", sum(v["bars"] for v in manifest.values()), "bars;",
          sum(1 for v in manifest.values() if v["funding_rows"]), "with funding")


if __name__ == "__main__":
    main()
