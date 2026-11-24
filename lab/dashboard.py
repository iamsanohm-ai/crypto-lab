"""สร้าง dashboard/data.json จากข้อมูลจริงเท่านั้น (Binance + state/ + ledger/ + research/).

ทุกส่วนมี source และเวลา; ไม่มีตัวเลขใดที่ไม่ได้มาจากข้อมูลจริง.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import yaml

from lab.data import API, ROOT, _get, now_iso

OUT = ROOT / "dashboard" / "data.json"
OUT_SITE = ROOT / "docs" / "data.json"  # GitHub Pages


def _klines(symbol="BTCUSDT", interval="4h", limit=700):
    raw = json.loads(_get(f"{API}/klines?symbol={symbol}&interval={interval}&limit={limit}"))
    df = pd.DataFrame(raw, columns=["t", "o", "h", "l", "c", "v", "ct", "qv", "n", "tb", "tq", "x"])
    for k in ("o", "h", "l", "c", "qv"):
        df[k] = df[k].astype(float)
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    df["closed"] = df["ct"] < now_ms
    c = df["c"]
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi14"] = 100 - 100 / (1 + g / lo)
    df["time"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%MZ")
    return df


def candles():
    df = _klines().tail(180)
    return [{"time": r.time, "open": r.o, "high": r.h, "low": r.l, "close": r.c, "quote_volume": round(r.qv),
             "ema20": round(r.ema20, 2), "ema200": round(r.ema200, 2), "rsi14": round(r.rsi14, 1),
             "closed": bool(r.closed)} for r in df.itertuples()]


def market(members):
    raw = json.loads(_get(f"{API}/ticker/24hr?symbols=" + json.dumps(members, separators=(",", ":"))))
    rows = [{"symbol": t["symbol"].replace("USDT", ""), "last": float(t["lastPrice"]),
             "change_24h_pct": round(float(t["priceChangePercent"]), 2),
             "high_24h": float(t["highPrice"]), "low_24h": float(t["lowPrice"]),
             "quote_volume_24h": round(float(t["quoteVolume"]))} for t in raw]
    return sorted(rows, key=lambda r: -r["quote_volume_24h"])


def ledger():
    p = ROOT / "ledger" / "decisions.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def build():
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    judge = json.loads((ROOT / "research" / "judge_results.json").read_text())
    led = ledger()
    roles = {s["name"]: s["role"] for s in cfg["strategies"]}

    equity, accounts, positions, risk = [], [], [], []
    for r in led:
        if r["event"] == "TICK" and r.get("strategy") in roles:
            equity.append({"time": r["ts"][:16] + "Z", "strategy": r["strategy"], "role": roles[r["strategy"]],
                           "equity": r["equity"]})
    members = []
    for s in cfg["strategies"]:
        p = ROOT / "state" / f"paper_{s['name']}.json"
        st = json.loads(p.read_text()) if p.exists() else {"cash": cfg["capital"], "positions": {}, "closed": [],
                                                              "halted": None, "loss_streak": 0,
                                                              "day_start_equity": cfg["capital"]}
        members = members or st.get("universe", {}).get("members", [])
        eq = st["cash"] + sum(x["qty"] * x["last_price"] for x in st["positions"].values())
        closed = st["closed"]
        mt = judge["results"][s["name"]]["metrics"]
        accounts.append({"strategy": s["name"], "role": s["role"], "params": json.dumps(s["params"]),
                         "equity": round(eq, 2), "start_capital": cfg["capital"],
                         "pnl": round(eq - cfg["capital"], 2), "pnl_pct": round((eq / cfg["capital"] - 1) * 100, 2),
                         "cash": round(st["cash"], 2), "open_positions": len(st["positions"]),
                         "closed_trades": len(closed),
                         "paper_win_rate_pct": round(100 * sum(c["pnl"] > 0 for c in closed) / len(closed), 1) if closed else None,
                         "bt_return_pct": round(mt["return"] * 100, 1), "bt_max_dd_pct": round(mt["max_dd"] * 100, 1),
                         "bt_sharpe": round(mt["sharpe"], 2), "bt_trades": mt["trades"],
                         "bt_win_rate_pct": round(mt["win_rate"] * 100, 1)})
        for sym, x in st["positions"].items():
            positions.append({"strategy": s["name"], "symbol": sym.replace("USDT", ""), "entry": x["entry"],
                              "last": x["last_price"], "qty": x["qty"], "stop": x["stop"], "target": x.get("target"),
                              "pnl": round(x["qty"] * x["last_price"] - x["cost"], 2), "since": x["entry_time"][:16] + "Z"})
        day_pnl_pct = (eq / st.get("day_start_equity", cfg["capital"]) - 1) * 100
        risk.append({"strategy": s["name"], "role": s["role"],
                     "day_pnl_pct": round(day_pnl_pct, 2), "daily_limit_pct": -cfg["sentinel"]["daily_loss_limit"] * 100,
                     "loss_streak": st.get("loss_streak", 0), "loss_streak_limit": cfg["sentinel"]["max_consecutive_losses"],
                     "exposure_pct": round(100 * sum(x["qty"] * x["last_price"] for x in st["positions"].values()) / eq, 1) if eq else 0,
                     "halted": bool(st.get("halted")), "halt_reason": (st.get("halted") or {}).get("reason", ""),
                     "resume_on": (st.get("halted") or {}).get("resume_on") or ""})

    events = []
    for r in reversed(led):
        e = r["event"]
        if e in ("BUY", "SELL", "SENTINEL_HALT", "SENTINEL_REJECT", "SENTINEL_RESUME", "ERROR", "GROK_REVIEW", "GROK_VETO") or \
                (e == "SIGNALS" and r.get("candidates")):
            events.append({"time": r["ts"][:16] + "Z", "event": e, "strategy": r.get("strategy", ""),
                           "role": r.get("role", ""), "symbol": (r.get("symbol") or "").replace("USDT", ""),
                           "price": r.get("price"), "pnl": r.get("pnl"),
                           "detail": ((r.get("decision", "") + " · ") if e == "GROK_REVIEW" else "") + str(r.get("reason") or r.get("error") or "") or ", ".join(r.get("candidates", []))})
        if len(events) >= 40:
            break
    last_tick = max((r["ts"] for r in led if r["event"] == "TICK"), default=None)

    bh = judge["benchmarks"]
    leaderboard = [{"name": n, "role": roles.get(n, ""), "return_pct": round(r["metrics"]["return"] * 100, 1),
                    "max_dd_pct": round(r["metrics"]["max_dd"] * 100, 1), "sharpe": round(r["metrics"]["sharpe"], 2),
                    "trades": r["metrics"]["trades"], "score": r["score"]["total"],
                    "status": roles.get(n) or ("passed" if r["metrics"]["return"] > 0 and r["metrics"]["sharpe"] > bh["btc_buy_hold"]["sharpe"] else "cut")}
                   for n, r in judge["results"].items()]
    for k, label in (("btc_buy_hold", "BTC buy & hold"), ("btc_dca_weekly", "BTC DCA weekly"), ("top20_equal_weight", "Top-20 equal weight")):
        leaderboard.append({"name": label, "role": "benchmark", "return_pct": round(bh[k]["return"] * 100, 1),
                            "max_dd_pct": round(bh[k]["max_dd"] * 100, 1), "sharpe": round(bh[k]["sharpe"], 2),
                            "trades": None, "score": None, "status": "benchmark"})
    leaderboard.sort(key=lambda r: -r["sharpe"])

    scan_p = ROOT / "dashboard" / "scanner.json"
    scanner = json.loads(scan_p.read_text()) if scan_p.exists() else None

    curves_p = ROOT / "research" / "bt_curves.json"
    curves = json.loads(curves_p.read_text()) if curves_p.exists() else []

    out = {
        "generated_at": now_iso(),
        "sources": {"candles": f"{API}/klines BTCUSDT 4h", "market": f"{API}/ticker/24hr",
                    "paper": "state/paper_*.json + ledger/decisions.jsonl", "backtest": "research/judge_results.json",
                    "oos_period": judge["oos_period"]},
        "status": [{"generated_at": now_iso(), "last_bot_tick": last_tick, "mode": cfg["mode"],
                    "btc_close": None, "btc_ema200": None}],
        "candles": candles(), "market": market(members or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
        "accounts": accounts, "equity": equity, "positions": positions, "risk": risk, "events": events,
        "leaderboard": leaderboard, "bt_curves": curves,
        "scanner": scanner,
    }
    last_closed = [c for c in out["candles"] if c["closed"]][-1]
    out["status"][0].update(btc_close=last_closed["close"], btc_ema200=last_closed["ema200"],
                            regime="up" if last_closed["close"] > last_closed["ema200"] else "down",
                            candle_time=last_closed["time"])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), default=str))
    OUT_SITE.parent.mkdir(exist_ok=True)
    OUT_SITE.write_text(OUT.read_text())
    return out


if __name__ == "__main__":
    o = build()
    print(OUT, OUT.stat().st_size, "bytes", {k: len(v) for k, v in o.items() if isinstance(v, list)})
