"""สร้าง docs/library.json สำหรับหน้า "คลังกลยุทธ์" บน dashboard — ทุกตัวเลขมาจากผล walk-forward ของ Judge."""
from __future__ import annotations

import inspect
import json

import numpy as np
import pandas as pd
import yaml

from lab.data import DATA, ROOT, now_iso
from lab.strategies import IDEAS

REPO = "https://github.com/iamsanohm-ai/crypto-lab/blob/main/lab/strategies.py"
KIND = {  # trend | reversion | breakout | other
    "donchian_breakout": "breakout", "squeeze_breakout": "breakout", "nr7_breakout": "breakout", "breakout_funding_filter": "breakout",
    "classic_breakout": "breakout", "vol_expansion_trend": "breakout", "keltner_trend": "trend", "trend_pullback": "trend",
    "golden_cross_50_200": "trend", "ema_9_21_cross": "trend", "ts_momentum": "trend", "xs_momentum_rotation": "trend",
    "relative_strength_vs_btc": "trend", "weekly_open_trend": "trend", "volume_spike_momentum": "trend", "btc_lead_lag": "trend",
    "classic_sma_crossover": "trend", "classic_trend_pullback": "trend", "classic_trend_stop5": "trend",
    "bb_mean_reversion_uptrend": "reversion", "bb_mean_reversion_any": "reversion", "rsi2_connors": "reversion",
    "capitulation_reversal": "reversion", "classic_rsi_reversion": "reversion", "classic_rsi_dip": "reversion",
    "range_grid": "reversion", "funding_negative_extreme": "other", "funding_reset_pullback": "other", "taker_buy_pressure": "other",
}
TITLE = {"keltner_trend": "Keltner Trend", "golden_cross_50_200": "Golden Cross", "breakout_funding_filter": "Breakout + Funding",
         "classic_sma_crossover": "SMA Crossover (คลาสสิก)", "classic_rsi_reversion": "RSI Reversion (คลาสสิก)",
         "classic_rsi_dip": "RSI Dip (คลาสสิก)", "classic_trend_pullback": "Trend Pullback (คลาสสิก)",
         "classic_breakout": "Breakout (คลาสสิก)", "classic_trend_stop5": "Trend + 5% Stop (คลาสสิก)"}


def curve(name: str, points: int) -> list[float]:
    p = DATA / f"wf_{name}.parquet"
    if not p.exists():
        return []
    e = pd.read_parquet(p)["equity"].resample("1D").last().dropna()
    idx = np.linspace(0, len(e) - 1, min(points, len(e))).round().astype(int)
    return [round(float(v), 2) for v in e.iloc[idx]]


def pl_ratio(name: str) -> float | None:
    p = DATA / f"wf_trades_{name}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p)
    w, l = t.loc[t.pnl > 0, "pnl"], t.loc[t.pnl <= 0, "pnl"]
    return round(float(w.mean() / -l.mean()), 2) if len(w) and len(l) and l.mean() < 0 else None


def code_line(name: str) -> int | None:
    try:
        return inspect.getsourcelines(IDEAS[name]["fn"])[1]
    except Exception:  # noqa: BLE001
        return None


def main():
    j = json.loads((ROOT / "research" / "judge_results.json").read_text())
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    roles = {s["name"]: s["role"] for s in cfg["strategies"]}
    bh = j["benchmarks"]["btc_buy_hold"]
    start, end = pd.Timestamp(j["oos_period"][0]), pd.Timestamp(j["oos_period"][1])
    years = max((end - start).days / 365.25, 0.1)
    bots = []
    for i, (name, r) in enumerate(j["results"].items(), 1):
        mt = r["metrics"]
        ret = mt["return"]
        role = roles.get(name)
        passed = ret > 0 and mt["sharpe"] > bh["sharpe"]
        line = code_line(name)
        bots.append({
            "id": f"B{i:02d}", "name": name, "title": TITLE.get(name, name.replace("_", " ").title()),
            "kind": KIND.get(name, "other"), "classic": name.startswith("classic_"),
            "status": role or ("passed" if passed else "cut"),
            "reason": r["reason"], "kills": r["kills"],
            "return_pct": round(ret * 100, 2), "annual_pct": round(((1 + ret) ** (1 / years) - 1) * 100, 2),
            "sharpe": round(mt["sharpe"], 2), "max_dd_pct": round(mt["max_dd"] * 100, 2),
            "win_rate_pct": round(mt["win_rate"] * 100, 1), "pl_ratio": pl_ratio(name), "trades": mt["trades"],
            "losing_streak": mt["longest_losing_streak"], "worst_month_pct": round(mt["worst_month"] * 100, 1),
            "params": (r.get("chosen") or [{}])[-1].get("params", {}),
            "spark": curve(name, 60), "curve": curve(name, 220),
            "code_url": f"{REPO}#L{line}" if line else REPO,
        })
    btc = pd.read_parquet(DATA / "klines" / "BTCUSDT.parquet").set_index("time")["close"]
    btc = btc[btc.index >= start].resample("1D").last().dropna()
    btc = btc / btc.iloc[0] * 500 * (1 - 0.0015)
    idx = np.linspace(0, len(btc) - 1, min(220, len(btc))).round().astype(int)
    out = {"generated_at": now_iso(), "period": [str(start.date()), str(end.date())], "years": round(years, 2),
           "costs": "ค่าธรรมเนียม 0.1% + slippage 0.05% ต่อขา", "data": "Binance spot 4h, Top 20 ตามสภาพคล่องรายเดือน (รวมเหรียญที่ถูกถอด)",
           "benchmark": {"title": "BTC ถือยาว", "return_pct": round(bh["return"] * 100, 2), "max_dd_pct": round(bh["max_dd"] * 100, 2),
                         "sharpe": round(bh["sharpe"], 2), "curve": [round(float(v), 2) for v in btc.iloc[idx]]},
           "bots": bots}
    (ROOT / "docs" / "library.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(len(bots), "bots →", ROOT / "docs" / "library.json")


if __name__ == "__main__":
    main()
