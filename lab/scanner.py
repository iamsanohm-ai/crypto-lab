"""สแกนทั้งกระดาน: ทุกคู่ USDT spot ที่เทรดอยู่บน Binance (ไม่รวม stablecoin / leveraged token)
คำนวณสถานะของแต่ละเหรียญจากแท่ง 4h ที่ปิดแล้ว และเช็คว่ากลยุทธ์ใน config ให้สัญญาณซื้อ/ขายหรือไม่

ผลลัพธ์: dashboard/scanner.json (dashboard อ่านไปแสดง) — ไม่ได้ส่งออเดอร์
บอทเทรดเฉพาะ universe ที่ผ่าน backtest (config: universe_top_n) — scanner มีไว้ "ดู" ทั้งกระดาน
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from lab.data import API, ROOT, _get, candidate_symbols, now_iso
from lab.live import build_live_market
from lab.strategies import IDEAS
from lab import plans as planmod

OUT = ROOT / "dashboard" / "scanner.json"
MIN_LIQUID_USDT = 2_000_000   # volume 24 ชม. ต่ำกว่านี้ = สภาพคล่องต่ำ (slippage สูง)


def scan() -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    tickers = {t["symbol"]: t for t in json.loads(_get(f"{API}/ticker/24hr?type=MINI"))}
    syms = [s for s in candidate_symbols().query("status == 'TRADING'")["symbol"] if s in tickers]
    m = build_live_market(syms, bars=300, with_funding=False)
    T = len(m.times) - 1
    c = m.df("close")
    ema200 = c.ewm(span=200, adjust=False, min_periods=200).mean()
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + g / lo)
    mom30 = c.pct_change(180, fill_method=None) * 100
    sigs = {}
    for s in cfg["strategies"]:
        try:
            sigs[s["name"]] = (s["role"], IDEAS[s["name"]]["fn"](m, **s["params"]))
        except Exception as e:  # noqa: BLE001
            print("signal failed", s["name"], e)
    btc_up = bool(c["BTCUSDT"].iloc[T] > ema200["BTCUSDT"].iloc[T]) if "BTCUSDT" in c else None

    rows = []
    for j, sym in enumerate(m.symbols):
        close = m.close[T, j]
        if np.isnan(close):
            continue
        t = tickers.get(sym, {})
        qv24 = float(t.get("quoteVolume", 0) or 0)
        e200 = ema200.iloc[T, j]
        buy = [role for name, (role, sg) in sigs.items() if bool(sg.entry[T, j])]
        sell = [role for name, (role, sg) in sigs.items() if sg.exit is not None and bool(sg.exit[T, j])]
        trend = None if np.isnan(e200) else ("up" if close > e200 else "down")
        liquid = qv24 >= MIN_LIQUID_USDT
        rng = np.nanmax(m.high[T - 180:T + 1, j]) / np.nanmin(m.low[T - 180:T + 1, j]) - 1 if T >= 180 else np.nan
        if not np.isnan(rng) and rng < 0.02:   # ราคาแทบไม่ขยับใน 30 วัน = stablecoin/token ผูกราคา → ไม่นับ
            continue
        if buy and liquid:
            status = "buy_signal"
        elif not liquid:
            status = "illiquid"
        elif trend == "up":
            status = "uptrend"
        elif trend == "down":
            status = "downtrend"
        else:
            status = "new"
        rows.append({
            "symbol": sym.replace("USDT", ""), "status": status, "price": float(close),
            "change_24h_pct": round(float(t.get("lastPrice", close)) / float(t.get("openPrice") or close) * 100 - 100, 2) if t else None,
            "quote_volume_24h": round(qv24), "vs_ema200_pct": None if np.isnan(e200) else round((close / e200 - 1) * 100, 1),
            "rsi14": None if np.isnan(rsi.iloc[T, j]) else round(float(rsi.iloc[T, j]), 1),
            "mom_30d_pct": None if np.isnan(mom30.iloc[T, j]) else round(float(mom30.iloc[T, j]), 1),
            "buy_signals": ", ".join(buy), "sell_signals": ", ".join(sell),
        })
    order = {"buy_signal": 0, "uptrend": 1, "downtrend": 2, "new": 3, "illiquid": 4}
    rows.sort(key=lambda r: (order[r["status"]], -(r["mom_30d_pct"] if r["mom_30d_pct"] is not None else -1e9)))
    counts = pd.Series([r["status"] for r in rows]).value_counts().to_dict()
    analysis = analyze(m, c, ema200, rsi, rows, btc_up, cfg)
    st_p = ROOT / "state" / f"paper_{cfg['strategies'][0]['name']}.json"
    universe = (json.loads(st_p.read_text()).get("universe") or {}).get("members", []) if st_p.exists() else []
    plans = planmod.build(m, rows, cfg, bool(btc_up), universe)
    try:
        planmod.alert_new(plans, str(m.times[T]))
    except Exception as e:  # noqa: BLE001
        print("plan alert failed", e)
    out = {"generated_at": now_iso(), "bar": str(m.times[T]), "btc_regime_up": btc_up, "total": len(rows),
           "counts": counts, "min_liquid_usdt": MIN_LIQUID_USDT, "analysis": analysis, "plans": plans, "rows": rows,
           "source": f"{API}/klines 4h + {API}/ticker/24hr (Binance spot, USDT pairs)"}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    return out


def analyze(m, c, ema200, rsi, rows, btc_up, cfg) -> dict:
    """บทวิเคราะห์ตลาดแบบกฎตายตัว (ไม่ใช้ AI) — ทุกประโยคมาจากตัวเลขจริงด้านล่าง."""
    T = len(m.times) - 1
    b = c["BTCUSDT"]
    btc_close, btc_e200 = float(b.iloc[T]), float(ema200["BTCUSDT"].iloc[T])
    btc_gap = (btc_close / btc_e200 - 1) * 100
    btc_mom30 = (btc_close / float(b.iloc[T - 180]) - 1) * 100 if T >= 180 else None
    btc_rsi = float(rsi["BTCUSDT"].iloc[T])
    r4 = b.pct_change(fill_method=None)
    vol_now = float(r4.iloc[T - 42:T + 1].std() * np.sqrt(6 * 365) * 100)          # 7 วันล่าสุด (annualized %)
    vol_base = float(r4.iloc[max(0, T - 270):T + 1].std() * np.sqrt(6 * 365) * 100)  # ~45 วัน
    vol_ratio = vol_now / vol_base if vol_base else 1.0
    liquid = [r for r in rows if r["status"] != "illiquid" and r["vs_ema200_pct"] is not None]
    up = [r for r in liquid if r["vs_ema200_pct"] > 0]
    breadth = 100 * len(up) / len(liquid) if liquid else 0.0
    with_mom = [r for r in liquid if r["mom_30d_pct"] is not None]
    leaders = sorted(with_mom, key=lambda r: -r["mom_30d_pct"])[:5]
    laggards = sorted(with_mom, key=lambda r: r["mom_30d_pct"])[:5]
    buys = [r for r in rows if r["status"] == "buy_signal"]

    if btc_up and breadth >= 50:
        regime, regime_th = "bull", "ขาขึ้น"
    elif not btc_up and breadth < 35:
        regime, regime_th = "bear", "ขาลง"
    else:
        regime, regime_th = "mixed", "ผสม / sideways"
    vol_th = "สูงกว่าปกติ" if vol_ratio > 1.3 else "ต่ำกว่าปกติ" if vol_ratio < 0.75 else "ปกติ"
    oversold = btc_rsi < 30
    overbought = btc_rsi > 70

    lines = [
        f"ภาพรวม: ตลาด{regime_th} — BTC {btc_close:,.0f} อยู่{'เหนือ' if btc_up else 'ใต้'} EMA200 (4h) {btc_gap:+.1f}%"
        + (f", 30 วัน {btc_mom30:+.1f}%" if btc_mom30 is not None else ""),
        f"ความกว้างตลาด: {len(up)} จาก {len(liquid)} เหรียญที่มีสภาพคล่อง ({breadth:.0f}%) อยู่เหนือ EMA200"
        + (" — ส่วนใหญ่ยังอ่อนแอ" if breadth < 35 else " — แข็งแรงทั่วกระดาน" if breadth >= 60 else ""),
        f"ความผันผวน BTC: {vol_now:.0f}% ต่อปี ({vol_th}, เทียบค่าเฉลี่ย ~45 วัน {vol_base:.0f}%)",
        f"RSI BTC (4h): {btc_rsi:.0f}" + (" — ขายมากเกินไป อาจเด้งระยะสั้น แต่ยังไม่ใช่สัญญาณกลับเป็นขาขึ้น" if oversold
                                         else " — ซื้อมากเกินไป ระวังการย่อ" if overbought else ""),
    ]
    if leaders:
        lines.append("แข็งสุด 30 วัน: " + ", ".join(f"{r['symbol']} {r['mom_30d_pct']:+.0f}%" for r in leaders))
    if laggards:
        lines.append("อ่อนสุด 30 วัน: " + ", ".join(f"{r['symbol']} {r['mom_30d_pct']:+.0f}%" for r in laggards))
    champ = cfg["strategies"][0]["name"]
    if buys:
        action = "บอท: มีสัญญาณซื้อ " + ", ".join(r["symbol"] for r in buys[:8]) + " — บอทจะเข้าเฉพาะเหรียญใน Top 20 ที่ผ่าน Sentinel"
    elif not btc_up:
        need = btc_e200 - btc_close
        action = (f"บอท: ถือเงินสด — กลยุทธ์หลัก ({champ}) รอให้ BTC กลับขึ้นเหนือ EMA200 (~{btc_e200:,.0f}, "
                  f"ห่างอีก {need:,.0f} หรือ {need / btc_close * 100:.1f}%) ตามที่ backtest แสดงว่าการเข้าในตลาดขาลงขาดทุน")
    else:
        action = "บอท: ตลาดเปิดให้เข้าได้ แต่ยังไม่มีเหรียญไหนเกิดสัญญาณ — รอแท่ง 4h ถัดไป"
    lines.append(action)
    return {"regime": regime, "regime_th": regime_th, "btc_close": btc_close, "btc_ema200": round(btc_e200, 2),
            "btc_vs_ema200_pct": round(btc_gap, 2), "btc_mom_30d_pct": None if btc_mom30 is None else round(btc_mom30, 2),
            "btc_rsi14": round(btc_rsi, 1), "btc_vol_annual_pct": round(vol_now, 1), "btc_vol_base_pct": round(vol_base, 1),
            "breadth_pct": round(breadth, 1), "liquid_coins": len(liquid), "liquid_up": len(up),
            "leaders": [r["symbol"] for r in leaders], "laggards": [r["symbol"] for r in laggards], "lines": lines}


if __name__ == "__main__":
    o = scan()
    print(o["total"], "coins", o["counts"], "| btc up:", o["btc_regime_up"])
    print("\n".join(o["analysis"]["lines"]))
