"""ตรวจการคำนวณเงินของเทรดเร็ว paper: ซื้อ → TP/SL → กำไรขาดทุนหลังค่าธรรมเนียม, gate และ Sentinel (ไม่เรียกเน็ต)."""
import numpy as np
import pandas as pd

import lab.scalper as sc


def mkbot(tmp_path, monkeypatch, gate_avg):
    monkeypatch.setattr(sc, "ROOT", tmp_path)
    bot = sc.Scalper(tmp_path)
    bot.P = {"id": "5m:momo_burst", "label": "t", "interval": "5m", "strategy": "momo_burst", "params": {"n": 36, "k": 3.0}, "exit": {"tp": 0.02, "sl": 0.01, "hold": 12}}
    bot.MODELS = [bot.P]
    bot.s["shadow_closed"] = [{"net_pct": gate_avg, "model": "5m:momo_burst"} for _ in range(30)]
    df = pd.DataFrame({"time": np.arange(260) * 300_000 + 10**12, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0})
    monkeypatch.setattr(sc, "bars5", lambda s: df)
    monkeypatch.setattr(sc, "signals", lambda d, n, p: np.r_[np.zeros(259, bool), True])
    bot.px = {c: 100.0 for c in sc.COINS}
    return bot


def test_buy_then_take_profit(tmp_path, monkeypatch):
    bot = mkbot(tmp_path, monkeypatch, 0.2)
    bot.on_bar()
    assert len(bot.s["positions"]) == 1
    p = bot.s["positions"][0]
    assert p["cost"] <= sc.MAX_NOTIONAL + 1e-9
    bot.px[p["sym"]] = 103.0; bot.check_exits()
    t = bot.s["trades"][0]
    exp = p["qty"] * 103.0 * (1 - sc.SLIP) * (1 - sc.FEE) - p["cost"]
    assert abs(t["pnl_usdt"] - round(exp, 4)) < 1e-6 and t["pnl_usdt"] > 0 and t["reason"] == "tp"


def test_gate_closed_means_shadow_only(tmp_path, monkeypatch):
    bot = mkbot(tmp_path, monkeypatch, -0.3)
    bot.on_bar()
    assert bot.s["positions"] == [] and len(bot.s["shadow"]) == len(sc.COINS) and bot.s["cash"] == sc.CAPITAL


def test_sentinel_three_losses(tmp_path, monkeypatch):
    bot = mkbot(tmp_path, monkeypatch, 0.2)
    for _ in range(3):
        bot.s["shadow_closed"] = [{"net_pct": 0.2, "model": "5m:momo_burst"} for _ in range(30)]   # ประตูยังเปิด
        bot.on_bar()
        for p in list(bot.s["positions"]): bot.px[p["sym"]] = 98.0
        bot.check_exits()
        for c in sc.COINS: bot.px[c] = 100.0
    assert bot.s["sentinel"]["loss_streak"] == 3 and bot.s["cash"] < sc.CAPITAL
    assert not bot.sentinel_ok() and bot.s["sentinel"]["halted"]["reason"].startswith("แพ้ติดกัน")


def test_breakeven_moves_stop_once():
    from lab.live import apply_breakeven
    p = {"entry": 100.0, "stop": 94.0, "risk_dist": 6.0, "high_close": 105.0}
    assert not apply_breakeven(p, 1.0, 0.0015) and p["stop"] == 94.0      # ยังไม่ถึง 1R
    p["high_close"] = 106.0
    assert apply_breakeven(p, 1.0, 0.0015) and abs(p["stop"] - 100.3) < 1e-9   # ทุน + ค่าธรรมเนียมไปกลับ
    assert not apply_breakeven(p, 1.0, 0.0015)                             # ทำครั้งเดียว
    assert not apply_breakeven({"entry": 1, "stop": 0.9, "high_close": 2}, 1.0, 0.0015)   # สถานะเก่าไม่มี risk_dist → ไม่แตะ


def test_active_model_trades_on_probation_and_gets_benched(tmp_path, monkeypatch):
    bot = mkbot(tmp_path, monkeypatch, -0.3)           # ผลเงาติดลบ → ประตูปิด
    bot.P["active"] = True
    bot.on_bar()
    assert len(bot.s["positions"]) == 1 and bot.s["positions"][0]["mode"] == "probation"   # ซื้อด้วยเงิน 1 เหรียญต่อแท่ง
    p = bot.s["positions"][0]
    assert p["cost"] <= sc.CAPITAL * sc.RISK_PROBATION / (0.01 + 2 * (sc.FEE + sc.SLIP)) * 1.01   # ขนาดครึ่งหนึ่ง รวมค่าธรรมเนียมในความเสี่ยง
    bot.s["positions"] = []; bot.s["cash"] = sc.CAPITAL
    bot.s["trades"] = [{"net_pct": -0.8, "model": bot.P["id"], "pnl_usdt": -1} for _ in range(20)]
    bot.on_bar()
    assert bot.s["positions"] == [] and bot.s["bench"][bot.P["id"]]   # แพ้ 20 ครั้งเฉลี่ยแย่ → พักใช้เงิน


def test_trailing_stop_locks_profit(tmp_path, monkeypatch):
    bot = mkbot(tmp_path, monkeypatch, 0.2)
    bot.P["exit"] = {"tp": 0.05, "sl": 0.01, "trail": 0.01, "hold": 12}
    bot.on_bar(); sym = bot.s["positions"][0]["sym"]
    bot.px[sym] = 100.5; bot.check_exits()                  # กำไรยังไม่พ้นค่าธรรมเนียม → stop ยังไม่ขยับ
    assert bot.s["positions"][0]["sl"] < bot.s["positions"][0]["entry"]
    bot.px[sym] = 103.0; bot.check_exits()                  # ราคาขึ้น → stop ขยับขึ้นมาเหนือทุน
    assert bot.s["positions"][0]["sl"] > bot.s["positions"][0]["entry"]
    bot.px[sym] = 101.5; bot.check_exits()
    t = [x for x in bot.s["trades"] if x["sym"] == sym][0]
    assert t["reason"] == "trail" and t["pnl_usdt"] > 0
