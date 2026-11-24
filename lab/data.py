"""ดึงข้อมูลจริงจาก Binance (public, ไม่ต้องใช้คีย์) — บันทึกแหล่งที่มาและเวลาทุกไฟล์.

แหล่งข้อมูล:
  - data-api.binance.vision : spot klines / exchangeInfo (market-data-only endpoint ของ Binance)
  - data.binance.vision     : ไฟล์ funding rate รายเดือนของ USDⓈ-M futures
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

API = "https://data-api.binance.vision/api/v3"
VISION = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
for _sub in ("", "klines", "funding"):
    (DATA / _sub).mkdir(parents=True, exist_ok=True)
STABLES = {"USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "PAX", "UST", "USDE", "AEUR", "GBP",
           "TRY", "BRL", "RLUSD", "USD1", "XUSD", "BFUSD", "PAXG", "WBTC", "WBETH", "EURI", "BNSOL", "USTC",
           "XAUT", "SNDKB", "SPCXB", "U", "RWUSD", "TSLAB", "USDS", "PYUSD", "XUSD",
           "SNXXB", "SOXLB", "NVDAB", "AAPLB", "MSTRB", "COINB", "QQQB", "SPYB"}  # หุ้น/ETF แบบ token  # ทองคำ/หุ้นแบบ token ไม่ใช่คริปโต
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR")


def _get(url: str, retries: int = 4):
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == retries - 1:
                raise
        except Exception:
            if i == retries - 1:
                raise
        time.sleep(2 ** i)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def candidate_symbols() -> pd.DataFrame:
    """ทุกคู่ USDT spot รวมที่หยุดเทรดแล้ว (status BREAK) เพื่อลด survivorship bias."""
    info = json.loads(_get(f"{API}/exchangeInfo?permissions=SPOT"))
    rows = []
    for s in info["symbols"]:
        base = s["baseAsset"]
        if not s["symbol"].isascii() or s["quoteAsset"] != "USDT" or base in STABLES or base.endswith(LEVERAGED) \
                or base.endswith("USD"):  # stablecoin เกือบทั้งหมดลงท้ายด้วย USD
            continue
        if any("TRD_GRP_261" in ps for ps in s.get("permissionSets", [])):  # หุ้น/ETF แบบ token (Binance จัดกลุ่มนี้)
            continue
        rows.append({"symbol": s["symbol"], "base": base, "status": s["status"]})
    return pd.DataFrame(rows)


def klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    out, cur = [], start_ms
    while cur < end_ms:
        raw = _get(f"{API}/klines?symbol={symbol}&interval={interval}&startTime={cur}&endTime={end_ms}&limit=1000")
        if not raw:
            break
        batch = json.loads(raw)
        if not batch:
            break
        out.extend(batch)
        cur = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades",
            "taker_base", "taker_quote", "ignore"]
    df = pd.DataFrame(out, columns=cols)
    if df.empty:
        return df
    for c in ("open", "high", "low", "close", "volume", "quote_volume", "taker_quote"):
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["time", "open", "high", "low", "close", "volume", "quote_volume", "taker_quote", "close_time"]]


def funding(symbol: str, months: list[str]) -> pd.DataFrame:
    def one(m):
        raw = _get(f"{VISION}/{symbol}/{symbol}-fundingRate-{m}.zip")
        if not raw:
            return []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            text = z.read(z.namelist()[0]).decode()
        rows = list(csv.reader(text.splitlines()))
        if rows and not rows[0][0].isdigit():
            rows = rows[1:]
        return [(int(r[0]), float(r[2])) for r in rows]

    with ThreadPoolExecutor(8) as pool:
        rows = [r for part in pool.map(one, months) for r in part]
    df = pd.DataFrame(rows, columns=["ts", "funding"]).drop_duplicates("ts").sort_values("ts")
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df[["time", "funding"]]
