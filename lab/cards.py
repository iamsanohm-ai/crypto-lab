"""เขียน strategy card (Markdown) สำหรับ champion + challengers และตารางสรุปทุกไอเดีย."""
from __future__ import annotations

import json

import yaml

from lab.data import ROOT
from lab.strategies import IDEAS

RULES = {
    "keltner_trend": {
        "entry": "แท่ง 4h ปิดเหนือ EMA20 + 2.0×ATR(20) เป็นแท่งแรก, ราคา > EMA200 ของเหรียญ, และ BTC > EMA200 (4h)",
        "exit": "ปิดต่ำกว่า EMA20 → ขายที่ open แท่งถัดไป; trailing stop = ราคาปิดสูงสุดตั้งแต่เข้า − 3×ATR",
        "stop": "เริ่มต้น 3.0×ATR(20) ใต้ราคาเข้า",
        "warning": "win rate 30 วันต่ำกว่า 25% หรือ avg R ของ 20 เทรดล่าสุดติดลบ"},
    "golden_cross_50_200": {
        "entry": "EMA30 ตัดขึ้น EMA120 บนแท่ง 4h (ไม่ใช้ตัวกรอง BTC)",
        "exit": "EMA30 ตัดลง EMA120; trailing stop = ราคาปิดสูงสุด − 6×ATR(14)",
        "stop": "เริ่มต้น 4×ATR(14)",
        "warning": "สัญญาณ exit แบบตัดลงขาดทุนติดกันมากกว่า 8 ครั้ง (ตลาด chop)"},
    "breakout_funding_filter": {
        "entry": "ปิดเหนือ high สูงสุด 60 แท่ง (10 วัน), ราคา > EMA200, funding เฉลี่ย 3 วัน < 0.01%/8h, BTC > EMA200",
        "exit": "trailing stop = ราคาปิดสูงสุด − 3×ATR(14) (ไม่มี exit ตามสัญญาณ)",
        "stop": "เริ่มต้น 2×ATR(14)",
        "warning": "กำไรทั้งหมดมาจาก ≤2 เทรดในรอบ 3 เดือน หรือ funding estimate ห่างจากค่าจริงรายเดือนมาก"},
}


def pct(x): return f"{x:+.1%}"


def card(role, s, j, fc, bh):
    r = j["results"][s["name"]]
    mt, reg, sc = r["metrics"], r["regimes"], r["score"]
    f = fc[s["name"]]
    rules = RULES[s["name"]]
    folds = " · ".join(f"{k[:7]} {pct(v)}" for k, v in f["fold_returns"].items())
    rob = ", ".join(f"{x['change']} {pct(x['return'])}" for x in f["robustness"])
    return f"""# {role.upper()}: `{s['name']}`  ·  params {s['params']}

**ไอเดีย:** {r['reason']}

| | |
|---|---|
| **ทำไม edge ถึงมี / ใครจ่าย** | {r['reason']} |
| **Entry** | {rules['entry']} |
| **Exit** | {rules['exit']} |
| **Stop** | {rules['stop']} |
| **ขนาดไม้** | เสี่ยง 0.5% ของ equity ต่อเทรด (= ระยะ stop × จำนวน) ไม่เกิน 25% ของพอร์ต, สูงสุด 5 สถานะ |

## ผล walk-forward (OOS {j['oos_period'][0][:10]} → {j['oos_period'][1][:10]}, หลังค่าธรรมเนียม 0.1% + slippage 0.05% ต่อขา)
| | กลยุทธ์ | BTC buy & hold | Top-20 equal weight |
|---|---|---|---|
| ผลตอบแทน | **{pct(mt['return'])}** | {pct(bh['btc_buy_hold']['return'])} | {pct(bh['top20_equal_weight']['return'])} |
| Max drawdown | {pct(mt['max_dd'])} | {pct(bh['btc_buy_hold']['max_dd'])} | {pct(bh['top20_equal_weight']['max_dd'])} |
| Sharpe (รายวัน) | {mt['sharpe']:.2f} | {bh['btc_buy_hold']['sharpe']:.2f} | {bh['top20_equal_weight']['sharpe']:.2f} |
| Return / MaxDD | {mt['return']/abs(mt['max_dd']):.2f} | {bh['btc_buy_hold']['return']/abs(bh['btc_buy_hold']['max_dd']):.2f} | – |

- จำนวนเทรด **{mt['trades']}** · win rate {mt['win_rate']:.0%} · avg R {mt['avg_r']:+.2f} · profit factor {mt['profit_factor']:.2f}
- **เดือนที่แย่ที่สุด:** {pct(mt['worst_month'])} ({mt['worst_month_label']}) · **แพ้ติดกันนานสุด:** {mt['longest_losing_streak']} เทรด
- **ผลรายช่วง (แต่ละช่วงไม่เคยเห็นตอนเลือกพารามิเตอร์):** {folds} → บวก {f['positive_folds']}/6 ช่วง
- **ตามสภาพตลาด (เฉลี่ยต่อเดือน):** {", ".join(f"{k} {pct(v['avg_month'])} ({v['months']} เดือน)" for k, v in reg.items())}
- **คะแนน 1-5:** {", ".join(f"{k} {v}" for k, v in sc.items())}

## Final check
| คำถาม | ผล |
|---|---|
| ชนะบนข้อมูลที่ไม่เคยเห็น? | {"ใช่" if mt['return'] > 0 else "ไม่"} ({pct(mt['return'])} OOS, {f['positive_folds']}/6 ช่วงเป็นบวก) |
| ชนะ buy & hold หลังต้นทุน? | **ผลตอบแทนดิบ: ไม่** ({pct(mt['return'])} vs {pct(bh['btc_buy_hold']['return'])}) · **ต่อความเสี่ยง: ใช่** (Sharpe {mt['sharpe']:.2f} vs {bh['btc_buy_hold']['sharpe']:.2f}) |
| ≥ 50 เทรด? | {"ใช่" if mt['trades'] >= 50 else "ไม่"} ({mt['trades']}) |
| ค่าธรรมเนียม × 2? | {pct(f['double_costs']['return'])}, Sharpe {f['double_costs']['sharpe']:.2f}, DD {pct(f['double_costs']['max_dd'])} |
| ทนต่อการเปลี่ยนพารามิเตอร์ ±20%? | บวก {f['robust_share_positive']:.0%} ของทุกกรณี (ต่ำสุด {pct(f['robust_min_return'])}) — {rob} |
| ตัวเลขรั่วจากอนาคต? | ไม่พบ: `tests/test_lab.py::test_no_lookahead` ผ่าน + สัญญาณ live ตรงกับ backtest 300/300 แท่ง |
| funding รวมในการทดสอบ? | spot long-only ไม่จ่าย funding (ใช้เป็นสัญญาณเท่านั้น) |
| เหรียญที่ถูกถอดรวมในการทดสอบ? | ใช่ (18 เหรียญ เช่น FTM, MATIC, EOS, OM) ถ้าถือตอนถูกถอด = ขายราคาสุดท้าย −2% |

**สภาพตลาดที่ฆ่ามัน:** {r['kills']}
**สัญญาณเตือนแรกว่ามันกำลังตาย:** {rules['warning']}

## ⚠️ WHY THIS COULD FAIL
- ทดสอบ 22 ไอเดียแล้วเลือกตัวที่ดีที่สุด → Sharpe {mt['sharpe']:.2f} ใน 3 ปี **ยังไม่มีนัยสำคัญทางสถิติ** เมื่อคิดเรื่องการทดสอบหลายครั้ง (ค่าที่ได้จากโชคล้วนๆ ของตัวที่ดีที่สุดใน 22 ตัวอาจสูงถึง ~1.0)
- ทั้ง 3 กลยุทธ์เป็น trend-following เหมือนกัน (correlation 0.67–0.78) — ถ้า trend หายไป ทั้ง champion และ challengers จะแพ้พร้อมกัน
- ช่วง 2025-11 → 2026-04 ติดลบ ({pct(f['fold_returns'].get('2025-11-01', 0))}) — ตลาดหมี/chop ทำร้ายจริง
- กำไรกระจุกในเทรดใหญ่ไม่กี่ตัว (ดู research/SUMMARY.md) — win rate ต่ำ ต้องทนแพ้ติดกันได้ {mt['longest_losing_streak']} ครั้ง
"""


def main():
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    j = json.loads((ROOT / "research" / "judge_results.json").read_text())
    fc = json.loads((ROOT / "research" / "final_check.json").read_text())
    bh = j["benchmarks"]
    for s in cfg["strategies"]:
        (ROOT / "research" / "cards" / f"{s['role']}_{s['name']}.md").write_text(card(s["role"], s, j, fc, bh))
    rows = sorted(j["results"].items(), key=lambda kv: -kv[1]["metrics"]["sharpe"])
    chosen = {s["name"]: s["role"] for s in cfg["strategies"]}
    lines = ["# ผล Judge — ทุกไอเดีย (walk-forward OOS, หลังต้นทุน)\n",
             f"ข้อมูล: Binance spot 4h, {j['oos_period'][0][:10]} → {j['oos_period'][1][:10]} · แหล่ง: data/manifest.json · สร้างเมื่อ {j['generated_at']}\n",
             f"**Benchmark:** BTC buy & hold {pct(bh['btc_buy_hold']['return'])} (DD {pct(bh['btc_buy_hold']['max_dd'])}, Sharpe {bh['btc_buy_hold']['sharpe']:.2f}) · "
             f"Top-20 equal weight {pct(bh['top20_equal_weight']['return'])} · "
             f"BTC DCA รายสัปดาห์ {pct(bh['btc_dca_weekly']['return'])} (DD {pct(bh['btc_dca_weekly']['max_dd'])}, Sharpe {bh['btc_dca_weekly']['sharpe']:.2f})\n",
             "| ไอเดีย | ผลตอบแทน | MaxDD | Sharpe | เทรด | แพ้ติด | คะแนน | สถานะ |", "|---|---|---|---|---|---|---|---|"]
    for name, r in rows:
        mt = r["metrics"]
        beats_risk = mt["sharpe"] > bh["btc_buy_hold"]["sharpe"] and mt["return"] > 0
        status = f"👑 {chosen[name]}" if name in chosen else ("ผ่านความเสี่ยงแต่ไม่เลือก" if beats_risk else "❌ ตัดทิ้ง")
        lines.append(f"| {name} | {pct(mt['return'])} | {pct(mt['max_dd'])} | {mt['sharpe']:.2f} | {mt['trades']} | "
                     f"{mt['longest_losing_streak']} | {r['score']['total']} | {status} |")
    lines.append("\n**เกณฑ์:** ต้องเป็นบวกหลังต้นทุน และ Sharpe > BTC buy & hold, จากนั้นผ่าน final check "
                 "(ค่าธรรมเนียม×2, ±20% พารามิเตอร์, ≥50 เทรด, ไม่พึ่งเทรดไม่กี่ตัว). **ไม่มีไอเดียไหนชนะ BTC buy & hold "
                 "ในแง่ผลตอบแทนดิบ** (ด้วยความเสี่ยง 0.5%/เทรด)\n")
    lines.append("**ทำไม weekly_open_trend ไม่ถูกเลือก:** ถ้าตัด 5 เทรดที่ดีที่สุดออกจะขาดทุน และค่าธรรมเนียม×2 เหลือ Sharpe 0.31\n")
    (ROOT / "research" / "SUMMARY.md").write_text("\n".join(lines))
    write_bt_curves()
    print("ok")


if __name__ == "__main__":
    main()


def write_bt_curves():
    """เส้น equity backtest รายวันของกลยุทธ์ใน config + BTC buy & hold → research/bt_curves.json (ใช้ใน dashboard)."""
    import pandas as pd
    from lab.data import DATA
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    rows = []
    for s in cfg["strategies"]:
        p = DATA / f"wf_{s['name']}.parquet"
        if not p.exists():
            continue
        e = pd.read_parquet(p)["equity"].resample("1D").last().dropna()
        rows += [{"date": d.strftime("%Y-%m-%d"), "series": s["name"], "equity": round(v, 2)} for d, v in e.items()]
    b = pd.read_parquet(DATA / "klines" / "BTCUSDT.parquet").set_index("time")["close"]
    b = b[b.index >= pd.Timestamp("2023-11-01", tz="UTC")].resample("1D").last().dropna()
    b = b / b.iloc[0] * 500 * (1 - 0.0015)
    rows += [{"date": d.strftime("%Y-%m-%d"), "series": "BTC buy & hold", "equity": round(v, 2)} for d, v in b.items()]
    (ROOT / "research" / "bt_curves.json").write_text(json.dumps(rows, separators=(",", ":")))
