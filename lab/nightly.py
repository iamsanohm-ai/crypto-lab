"""Judge อัตโนมัติทุกคืน (ไม่ใช้ AI): backtest ทุกไอเดีย → final check ตัวที่รอด → cards → เสนอเปลี่ยน champion ถ้ามีตัวที่ดีกว่าชัดเจน."""
from __future__ import annotations

import json

import yaml

from lab import cards, final_check, judge
from lab.data import ROOT, now_iso


def main():
    judge.run()
    j = json.loads((ROOT / "research" / "judge_results.json").read_text())
    bh = j["benchmarks"]["btc_buy_hold"]
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    chosen = [s["name"] for s in cfg["strategies"]]
    survivors = [n for n, r in j["results"].items() if r["metrics"]["return"] > 0 and r["metrics"]["sharpe"] > bh["sharpe"]]
    final_check.main(sorted(set(survivors) | set(chosen)))
    cards.main()
    fc = json.loads((ROOT / "research" / "final_check.json").read_text())

    def passes(n):
        f, m = fc.get(n), j["results"][n]["metrics"]
        return bool(f) and m["trades"] >= 50 and f["positive_folds"] >= 4 and f["robust_share_positive"] == 1.0 \
            and f["double_costs"]["sharpe"] > bh["sharpe"]

    champ = chosen[0]
    champ_sh = j["results"][champ]["metrics"]["sharpe"]
    notes = []
    for n in survivors:
        if n not in chosen and passes(n) and j["results"][n]["metrics"]["sharpe"] > champ_sh:
            notes.append(f"- ข้อเสนอ: `{n}` Sharpe {j['results'][n]['metrics']['sharpe']:.2f} > champion `{champ}` {champ_sh:.2f} และผ่าน final check ทุกข้อ")
    for n in chosen:
        if n not in survivors:
            notes.append(f"- เตือน: `{n}` (ใน config) ไม่ผ่านเกณฑ์แล้วในการทดสอบคืนนี้ — พิจารณาตัดออก")
    if notes:
        p = ROOT / "research" / "DECISION.md"
        old = p.read_text() if p.exists() else ""
        p.write_text(f"Judge อัตโนมัติ {now_iso()[:10]}:\n" + "\n".join(notes) + "\n\n" + old)
    print("survivors:", survivors, "| notes:", len(notes))


if __name__ == "__main__":
    main()
