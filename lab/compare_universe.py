"""เทียบผล walk-forward ของกลยุทธ์ใน config เมื่อเทรดใน Top 20 / 50 / 100 → research/universe_compare.json"""
import json

import yaml

from lab.data import DATA, ROOT, now_iso
from lab.engine import load_market, metrics
from lab.judge import benchmarks, idx, FOLDS, walk_forward


def main():
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    out = {"generated_at": now_iso(), "results": {}}
    for n in (20, 50, 100):
        m = load_market(top_n=n)
        bh, _ = benchmarks(m, idx(m, FOLDS[0][1]))
        res = {}
        for s in cfg["strategies"]:
            mt = metrics(walk_forward(m, s["name"]))
            res[s["name"]] = {k: mt[k] for k in ("return", "max_dd", "sharpe", "trades", "win_rate", "longest_losing_streak")}
            print(n, s["name"], {k: round(v, 3) if isinstance(v, float) else v for k, v in res[s["name"]].items()}, flush=True)
        out["results"][f"top{n}"] = {"strategies": res, "equal_weight": bh["top20_equal_weight"]["return"]}
    (ROOT / "research" / "universe_compare.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
