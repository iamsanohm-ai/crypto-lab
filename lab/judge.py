"""Judge: walk-forward backtest ทุกไอเดีย, ให้คะแนน 1-5, ตัดตัวที่ไม่ผ่าน, เขียน strategy card."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lab.data import DATA, ROOT, now_iso
from lab.engine import Costs, Risk, Result, load_market, metrics, simulate
from lab.strategies import IDEAS

OUT = ROOT / "research"
FOLDS = [("2022-11-01", "2023-11-01", "2024-05-01"), ("2023-05-01", "2024-05-01", "2024-11-01"),
         ("2023-11-01", "2024-11-01", "2025-05-01"), ("2024-05-01", "2025-05-01", "2025-11-01"),
         ("2024-11-01", "2025-11-01", "2026-05-01"), ("2025-05-01", "2026-05-01", "2099-01-01")]
MIN_TRAIN_TRADES = 10


def idx(m, date):
    return int(m.times.searchsorted(pd.Timestamp(date, tz="UTC")))


def train_score(r: dict) -> float:
    if r["trades"] < MIN_TRAIN_TRADES:
        return -np.inf
    return r["return"] / max(abs(r["max_dd"]), 0.02)


def walk_forward(m, name, costs=Costs(), risk=Risk(), fixed_params=None, sig_cache=None):
    spec = IDEAS[name]
    sig_cache = sig_cache if sig_cache is not None else {}

    def sig(params):
        key = json.dumps(params, sort_keys=True)
        if key not in sig_cache:
            sig_cache[key] = spec["fn"](m, **params)
        return sig_cache[key]

    equity_parts, trades, chosen = [], [], []
    scale = risk.capital
    for tr_s, te_s, te_e in FOLDS:
        a, b, c = idx(m, tr_s), idx(m, te_s), min(idx(m, te_e), len(m.times))
        if fixed_params is not None:
            best = fixed_params
        else:
            best, best_sc = spec["grid"][0], -np.inf
            for p in spec["grid"]:
                sc = train_score(metrics(simulate(m, sig(p), a, b, costs, risk)))
                if sc > best_sc:
                    best, best_sc = p, sc
        res = simulate(m, sig(best), b, c, costs, replace(risk, capital=scale))
        equity_parts.append(res.equity)
        if len(res.trades):
            trades.append(res.trades.assign(fold=te_s))
        scale = float(res.equity.iloc[-1])
        chosen.append({"test_start": te_s, "params": best})
    eq = pd.concat(equity_parts)
    tr = pd.concat(trades) if trades else pd.DataFrame(columns=["pnl", "r", "bars", "exit_time"])
    return Result(eq, tr, {"chosen": chosen})


def benchmarks(m, start, costs=Costs()):
    c = m.df("close")
    btc = c["BTCUSDT"].iloc[start:]
    btc_eq = btc / btc.iloc[0] * (1 - costs.per_side) ** 2
    # equal-weight universe (point-in-time) rebalanced monthly
    rets = c.pct_change(fill_method=None).iloc[start:]
    mem = m.df("member").iloc[start:].shift(1, fill_value=False)
    ew = (rets.where(mem).mean(axis=1)).fillna(0)
    ew_eq = (1 + ew).cumprod() * (1 - costs.per_side) ** 2
    # DCA: แบ่งเงินซื้อ BTC เท่าๆ กันทุกสัปดาห์ตลอดช่วงทดสอบ (เงินที่ยังไม่ซื้อถือเป็นเงินสด)
    weeks = list(range(0, len(btc), 7 * 6))
    per = 1.0 / len(weeks)
    units, cash, dca = 0.0, 1.0, []
    for i, px in enumerate(btc.to_numpy()):
        if i in weeks:
            units += per * (1 - costs.per_side) / px
            cash -= per
        dca.append(cash + units * px)
    dca_eq = pd.Series(dca, index=btc.index)
    out = {}
    for k, e in (("btc_buy_hold", btc_eq), ("top20_equal_weight", ew_eq), ("btc_dca_weekly", dca_eq)):
        out[k] = metrics(Result(e * 500, pd.DataFrame()))
        out[k].pop("trades"), out[k].pop("win_rate")
    return out, btc


def regime_perf(eq: pd.Series, btc: pd.Series) -> dict:
    bm = btc.resample("ME").last().pct_change()
    bm.iloc[0] = btc.resample("ME").last().iloc[0] / btc.iloc[0] - 1
    sm = eq.resample("ME").last()
    sret = sm.pct_change()
    sret.iloc[0] = sm.iloc[0] / eq.iloc[0] - 1
    lab_ = pd.cut(bm, [-np.inf, -0.05, 0.05, np.inf], labels=["bear", "chop", "bull"])
    df = pd.DataFrame({"s": sret, "r": lab_}).dropna()
    return {k: {"avg_month": float(g["s"].mean()), "months": int(len(g))} for k, g in df.groupby("r", observed=True)}


def score(mt: dict, reg: dict, bh: dict) -> dict:
    s = {}
    excess = mt["return"] - bh["btc_buy_hold"]["return"]
    s["wf_profit"] = 1 if mt["return"] <= 0 else 2 if excess <= 0 else 3 if mt["sharpe"] < 0.7 else 4 if mt["sharpe"] < 1.2 else 5
    dd = abs(mt["max_dd"])
    s["max_dd"] = 5 if dd < 0.05 else 4 if dd < 0.10 else 3 if dd < 0.15 else 2 if dd < 0.25 else 1
    n = mt["trades"]
    s["trades"] = 1 if n < 30 else 2 if n < 50 else 3 if n < 100 else 4 if n < 200 else 5
    st = mt["longest_losing_streak"]
    s["losing_streak"] = 5 if st <= 4 else 4 if st <= 6 else 3 if st <= 9 else 2 if st <= 13 else 1
    worst = min(reg.get("bear", {}).get("avg_month", 0), reg.get("chop", {}).get("avg_month", 0))
    s["bear_chop"] = 5 if worst >= 0.005 else 4 if worst >= 0 else 3 if worst >= -0.005 else 2 if worst >= -0.015 else 1
    s["total"] = round(float(np.mean(list(s.values()))), 2)
    return s


def run(names=None):
    t0 = time.time()
    exclude = set(json.loads((DATA / "exclude.json").read_text())) if (DATA / "exclude.json").exists() else set()
    m = load_market(exclude)
    oos_start = idx(m, FOLDS[0][1])
    bh, btc = benchmarks(m, oos_start)
    results = {}
    for name in names or IDEAS:
        cache = {}
        r = walk_forward(m, name, sig_cache=cache)
        mt = metrics(r)
        reg = regime_perf(r.equity, btc)
        sc = score(mt, reg, bh)
        beats = mt["return"] > bh["btc_buy_hold"]["return"] and mt["return"] > 0
        results[name] = {"reason": IDEAS[name]["reason"], "kills": IDEAS[name]["kills"], "metrics": mt,
                         "regimes": reg, "score": sc, "beats_buy_hold": beats, "chosen": r.meta["chosen"]}
        r.equity.to_frame("equity").to_parquet(DATA / f"wf_{name}.parquet")
        if len(r.trades):
            r.trades.to_parquet(DATA / f"wf_trades_{name}.parquet")
        print(f"{name:28s} ret={mt['return']:+7.1%} dd={mt['max_dd']:+6.1%} sh={mt['sharpe']:5.2f} "
              f"n={mt['trades']:4d} win={mt['win_rate']:.0%} streak={mt['longest_losing_streak']:2d} "
              f"score={sc['total']} beatsBH={beats}  ({time.time() - t0:.0f}s)", flush=True)
    out = {"generated_at": now_iso(), "oos_period": [str(m.times[oos_start]), str(m.times[-1])],
           "costs": {"fee_per_side": Costs().fee, "slippage_per_side": Costs().slippage},
           "risk": Risk().__dict__, "benchmarks": bh, "data_manifest": "data/manifest.json", "results": results}
    (OUT / "judge_results.json").write_text(json.dumps(out, indent=1, default=str))
    print("BENCH", json.dumps(bh, default=str))


if __name__ == "__main__":
    run(sys.argv[1:] or None)
