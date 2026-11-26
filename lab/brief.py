"""Morning brief (07:30) และ weekly review (อาทิตย์) — สร้างข้อความจากข้อมูลจริงใน state/ledger เท่านั้น."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import yaml

from lab.data import API, ROOT, _get

CFG = ROOT / "config" / "strategy.yaml"


def ledger(since: datetime | None = None) -> list[dict]:
    p = ROOT / "ledger" / "decisions.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return [r for r in rows if not since or datetime.fromisoformat(r["ts"]) >= since]


def market_lines() -> list[str]:
    out = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        t = json.loads(_get(f"{API}/ticker/24hr?symbol={s}"))
        out.append(f"{s[:-4]} {float(t['lastPrice']):,.2f} ({float(t['priceChangePercent']):+.2f}% 24h)")
    k = json.loads(_get(f"{API}/klines?symbol=BTCUSDT&interval=4h&limit=400"))
    c = pd.Series([float(x[4]) for x in k])
    e200 = c.ewm(span=200, adjust=False).mean().iloc[-1]
    regime = "ขาขึ้น (BTC > EMA200 4h) → กลยุทธ์ long เปิดได้" if c.iloc[-1] > e200 else \
        f"ขาลง (BTC {c.iloc[-1]:,.0f} < EMA200 {e200:,.0f}) → champion/challenger_2 จะไม่เปิดสถานะใหม่"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [" · ".join(out) + f"  [Binance, {stamp}]", f"Regime: {regime}"]


def account(name: str, cfg) -> dict:
    p = ROOT / "state" / f"paper_{name}.json"
    if not p.exists():
        return {"equity": cfg["capital"], "positions": {}, "closed": [], "halted": None}
    st = json.loads(p.read_text())
    st["equity"] = st["cash"] + sum(x["qty"] * x["last_price"] for x in st["positions"].values())
    return st


def morning():
    cfg = yaml.safe_load(CFG.read_text())
    judge = json.loads((ROOT / "research" / "judge_results.json").read_text())
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    led = ledger(since)
    lines = ["☀️ Crypto Lab — Morning brief", "", "ตลาด:"] + market_lines()
    sp, dp = ROOT / "dashboard" / "scanner.json", ROOT / "dashboard" / "data.json"
    src = json.loads(sp.read_text()) if sp.exists() else ((json.loads(dp.read_text()).get("scanner") or {}) if dp.exists() else {})
    if src:
        an = src.get("analysis") or {}
        if an.get("lines"):
            lines += ["", "วิเคราะห์ตลาด (ทั้งกระดาน):"] + ["• " + x for x in an["lines"]]
    lines += ["", "กลยุทธ์ (backtest OOS 3 ปี | paper ตั้งแต่เริ่ม):"]
    flags = []
    for s in cfg["strategies"]:
        mt = (judge.get("results", {}).get(s["name"]) or {}).get("metrics") or {"return": float("nan"), "max_dd": float("nan"), "sharpe": float("nan"), "trades": 0, "win_rate": float("nan")}   # กลยุทธ์ใหม่ยังไม่มีผล Judge
        a = account(s["name"], cfg)
        pnl = a["equity"] - cfg["capital"]
        lines.append(f"• {s['role']}: {s['name']} | BT {mt['return']:+.1%}, DD {mt['max_dd']:.1%}, Sharpe {mt['sharpe']:.2f} "
                     f"| paper {a['equity']:.2f} USDT ({pnl:+.2f}), ถือ {len(a['positions'])}, ปิดแล้ว {len(a['closed'])}")
        if a.get("halted"):
            flags.append(f"{s['name']} ถูก Sentinel หยุด: {a['halted']['reason']}")
    trades = [r for r in led if r["event"] in ("BUY", "SELL")]
    lines += ["", f"เทรด 24 ชม.ล่าสุด ({len(trades)}):"]
    lines += [f"  {r['ts'][11:16]} {r.get('role','')} {r['event']} {r['symbol']} @ {r['price']:.6g}"
              + (f" P&L {r['pnl']:+.2f}" if 'pnl' in r else "") + f" — {r.get('reason','')}" for r in trades] or ["  ไม่มี"]
    day_pnl = sum(r.get("pnl", 0) for r in trades if r["event"] == "SELL")
    lines.append(f"P&L ที่รับรู้ 24 ชม.: {day_pnl:+.2f} USDT")
    flags += [f"{r.get('strategy')}: {r['event']} {r.get('reason', r.get('error',''))}" for r in led
              if r["event"] in ("SENTINEL_HALT", "SENTINEL_REJECT", "ERROR")]
    ticks = [r for r in led if r["event"] == "TICK"]
    if len(ticks) < 18 * len(cfg["strategies"]):  # ควรมี ~24 รอบ/กลยุทธ์
        flags.append(f"บอทรันแค่ {len(ticks) // max(len(cfg['strategies']),1)} รอบใน 24 ชม. (ควร ~24)")
    lines += ["", "Sentinel:"] + ([f"  ⚠️ {f}" for f in flags[:8]] or ["  ปกติ ไม่มีอะไรผิดปกติ"])
    decision = (ROOT / "research" / "DECISION.md")
    lines += ["", "การตัดสินใจที่ต้องการจากคุณวันนี้:", "  " + (decision.read_text().strip() if decision.exists() else "ไม่มี")]
    return "\n".join(lines)


def weekly():
    cfg = yaml.safe_load(CFG.read_text())
    judge = json.loads((ROOT / "research" / "judge_results.json").read_text())
    lines = ["📊 Crypto Lab — Weekly review", ""]
    rows = []
    for s in cfg["strategies"]:
        a = account(s["name"], cfg)
        closed = pd.DataFrame(a["closed"])
        mt = (judge.get("results", {}).get(s["name"]) or {}).get("metrics") or {"return": float("nan"), "max_dd": float("nan"), "sharpe": float("nan"), "trades": 0, "win_rate": float("nan")}   # กลยุทธ์ใหม่ยังไม่มีผล Judge
        paper_ret = a["equity"] / cfg["capital"] - 1
        wr = (closed["pnl"] > 0).mean() if len(closed) else float("nan")
        rows.append((s, paper_ret, len(closed), wr, mt))
        lines.append(f"• {s['role']} {s['name']}: paper {paper_ret:+.2%} ({len(closed)} เทรด, win {wr:.0%}) "
                     f"vs backtest win {mt['win_rate']:.0%}, avg R {mt['avg_r']:+.2f}")
    champ = rows[0]
    best = max(rows[1:], key=lambda r: r[1])
    started = cfg["strategies"][0].get("crowned", "")
    days = (datetime.now(timezone.utc).date() - datetime.fromisoformat(started).date()).days if started else 0
    lines.append("")
    if days >= 7 and best[1] > champ[1] and best[2] >= 5:
        lines.append(f"🔁 ข้อเสนอ: {best[0]['name']} ชนะ champion มา {days} วัน → เสนอเปลี่ยน champion (ต้องให้คุณอนุมัติ)")
    else:
        lines.append(f"Champion คงเดิม (paper {days} วัน; challenger ต้องชนะหลัง 7 วันและมี ≥5 เทรด)")
    lines.append("Edge ที่จางลง: เทียบ win rate/avg R ของ paper กับ backtest ด้านบน — ถ้าต่ำกว่าครึ่งของ backtest 2 สัปดาห์ติด ให้ตัด")
    return "\n".join(lines)


if __name__ == "__main__":
    print(weekly() if "weekly" in sys.argv else morning())
