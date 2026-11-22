"""final_check จาก prompt: ชนะบนข้อมูลที่ไม่เคยเห็นไหม? หลังค่าธรรมเนียม×2? ≥50 เทรด? ทนต่อการเปลี่ยนพารามิเตอร์ไหม?"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace

import numpy as np
import pandas as pd

from lab.data import DATA, ROOT
from lab.engine import Costs, load_market, metrics
from lab.judge import FOLDS, idx, walk_forward
from lab.strategies import IDEAS
import inspect


def perturb(params: dict, fn) -> list[dict]:
    """±20% ทีละพารามิเตอร์ รวมพารามิเตอร์ default ที่ไม่ได้อยู่ใน grid (stop, trail ...)."""
    full = {k: v.default for k, v in inspect.signature(fn).parameters.items() if k != "m"}
    full.update(params)
    out = []
    for k, v in full.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v != 0:
            for f in (0.8, 1.2):
                nv = type(v)(round(v * f)) if isinstance(v, int) else v * f
                if nv != v:
                    out.append({**full, k: nv, "_changed": f"{k}×{f}"})
    return out


def main(names):
    exclude = set(json.loads((DATA / "exclude.json").read_text())) if (DATA / "exclude.json").exists() else set()
    m = load_market(exclude)
    judge = json.loads((ROOT / "research" / "judge_results.json").read_text())
    report = {}
    curves = {}
    for name in names:
        base = judge["results"][name]
        chosen = Counter(json.dumps(c["params"], sort_keys=True) for c in base["chosen"]).most_common(1)[0][0]
        params = json.loads(chosen)
        r2 = walk_forward(m, name, costs=Costs(fee=0.002, slippage=0.001))
        m2 = metrics(r2)
        fold_rets = {}
        eq = pd.read_parquet(DATA / f"wf_{name}.parquet")["equity"]
        curves[name] = eq
        for _, te_s, te_e in FOLDS:
            seg = eq[(eq.index >= pd.Timestamp(te_s, tz="UTC")) & (eq.index < pd.Timestamp(te_e, tz="UTC"))]
            fold_rets[te_s] = float(seg.iloc[-1] / seg.iloc[0] - 1) if len(seg) else None
        robust = []
        for p in perturb(params, IDEAS[name]["fn"]):
            tag = p.pop("_changed")
            mt = metrics(walk_forward(m, name, fixed_params=p))
            robust.append({"change": tag, "return": mt["return"], "sharpe": mt["sharpe"], "max_dd": mt["max_dd"]})
        fixed = metrics(walk_forward(m, name, fixed_params=params))
        report[name] = {
            "most_chosen_params": params, "chosen_per_fold": base["chosen"],
            "base": {k: base["metrics"][k] for k in ("return", "max_dd", "sharpe", "trades")},
            "fixed_params_full_oos": {k: fixed[k] for k in ("return", "max_dd", "sharpe", "trades")},
            "double_costs": {k: m2[k] for k in ("return", "max_dd", "sharpe", "trades")},
            "fold_returns": fold_rets,
            "positive_folds": sum(1 for v in fold_rets.values() if v and v > 0),
            "robustness": robust,
            "robust_share_positive": float(np.mean([x["return"] > 0 for x in robust])) if robust else None,
            "robust_min_return": float(min(x["return"] for x in robust)) if robust else None,
        }
        print(name, json.dumps({k: v for k, v in report[name].items() if k not in ("robustness", "chosen_per_fold")},
                               default=str), flush=True)
    daily = pd.DataFrame({k: v.resample("1D").last().pct_change() for k, v in curves.items()}).dropna()
    report["_correlation"] = daily.corr().round(2).to_dict()
    print("CORR\n", daily.corr().round(2))
    (ROOT / "research" / "final_check.json").write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
