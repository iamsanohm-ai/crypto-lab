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
    assert len(bot.s["positions"]) == sc.MAX_POS
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
    bot.on_bar()
    for p in list(bot.s["positions"]): bot.px[p["sym"]] = 98.0
    bot.check_exits()
    assert bot.s["sentinel"]["loss_streak"] == 3 and bot.s["cash"] < sc.CAPITAL
    assert not bot.sentinel_ok() and bot.s["sentinel"]["halted"]["reason"].startswith("แพ้ติดกัน")
