"""โหลดไฟล์ config (YAML) + อ่าน API key จาก environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "exchange": {"id": "binance", "sandbox": False},
    "watchlist": ["BTC/USDT", "ETH/USDT"],
    "alerts": [],
    "notify": {"telegram": False},
    "bot": {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "strategy": "ma_cross",
        "fast": 9,
        "slow": 21,
        "rsi_period": 14,
        "rsi_buy_below": 70,
        "order_quote_amount": 50,
        "stop_loss_pct": 3.0,
        "take_profit_pct": 6.0,
        "max_position_quote": 500,
        "poll_seconds": 60,
        "paper_starting_quote": 1000,
    },
    "db_path": "crypto_assist.db",
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None) -> dict[str, Any]:
    cfg = DEFAULT_CONFIG
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            cfg = _merge(DEFAULT_CONFIG, yaml.safe_load(f) or {})
    return cfg


def exchange_credentials(exchange_id: str) -> dict[str, str]:
    """อ่านคีย์จาก env เช่น BINANCE_API_KEY / BINANCE_SECRET (ห้ามใส่คีย์ในไฟล์ config)."""
    prefix = exchange_id.upper()
    creds = {}
    for field, env in (("apiKey", "API_KEY"), ("secret", "SECRET"), ("password", "PASSWORD")):
        val = os.environ.get(f"{prefix}_{env}")
        if val:
            creds[field] = val
    return creds
