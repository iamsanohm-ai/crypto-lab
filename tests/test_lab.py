"""ทดสอบ engine และตรวจ lookahead (สัญญาณต้องไม่ใช้ข้อมูลอนาคต)."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from lab.engine import Costs, Market, Risk, Signals, metrics, simulate
from lab.strategies import IDEAS


def synth_market(T=1500, S=4, seed=0):
    rng = np.random.default_rng(seed)
    times = pd.date_range("2023-01-01", periods=T, freq="4h", tz="UTC")
    rets = rng.normal(0.0003, 0.02, (T, S))
    close = 100 * np.exp(np.cumsum(rets, axis=0))
    open_ = np.vstack([close[:1], close[:-1]])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, (T, S)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, (T, S)))
    qv = rng.uniform(1e6, 5e6, (T, S))
    fund = rng.normal(0.0001, 0.0003, (T, S))
    syms = ["BTCUSDT"] + [f"C{i}USDT" for i in range(1, S)]
    return Market(times, syms, open_, high, low, close, qv, qv * rng.uniform(0.4, 0.7, (T, S)), fund,
                  np.ones((T, S), bool), np.full(S, T - 1))


def truncate(m: Market, t: int) -> Market:
    cut = lambda a: a[: t + 1]
    return Market(m.times[: t + 1], m.symbols, cut(m.open), cut(m.high), cut(m.low), cut(m.close), cut(m.qvol),
                  cut(m.taker), cut(m.funding), cut(m.member), np.minimum(m.last_bar, t))


@pytest.mark.parametrize("name", list(IDEAS))
def test_no_lookahead(name):
    m = synth_market()
    params = IDEAS[name]["grid"][0]
    full = IDEAS[name]["fn"](m, **params)
    for t in (700, 1100, 1499):
        part = IDEAS[name]["fn"](truncate(m, t), **params)
        np.testing.assert_array_equal(full.entry[t], part.entry[t], err_msg=f"{name} entry leaks at {t}")
        np.testing.assert_allclose(full.stop_dist[t], part.stop_dist[t], equal_nan=True)
        if full.exit is not None:
            np.testing.assert_array_equal(full.exit[t], part.exit[t])


def test_stop_and_costs():
    m = synth_market(T=10, S=1)
    m.open[:] = m.high[:] = m.low[:] = m.close[:] = 100.0
    m.low[5] = 90  # โดน stop แท่งที่ 5
    entry = np.zeros((10, 1), bool); entry[1] = True
    r = simulate(m, Signals(entry, np.full((10, 1), 5.0)), 0, 10, Costs(0.001, 0.0005), Risk(capital=1000))
    t = r.trades.iloc[0]
    assert t["reason"] == "stop" and t["exit"] == 95
    # risk 0.5% of 1000 = 5 USDT / (5/100) = 100 notional
    assert t["cost"] == pytest.approx(100 * 1.0015)
    assert r.equity.iloc[-1] < 1000 - 5   # ขาดทุนเกิน 1R นิดหน่อยเพราะค่าธรรมเนียม


def test_same_bar_stop_beats_target():
    m = synth_market(T=6, S=1)
    m.open[:] = m.close[:] = 100.0; m.high[:] = 100; m.low[:] = 100
    m.high[3], m.low[3] = 120, 90
    entry = np.zeros((6, 1), bool); entry[1] = True
    r = simulate(m, Signals(entry, np.full((6, 1), 5.0), target_r=2), 0, 6)
    assert r.trades.iloc[0]["reason"] == "stop"


def test_delisted_haircut():
    m = synth_market(T=10, S=1)
    m.open[:] = m.high[:] = m.low[:] = m.close[:] = 100.0
    for a in (m.open, m.high, m.low, m.close):
        a[6:] = np.nan
    m.last_bar[:] = 5
    entry = np.zeros((10, 1), bool); entry[1] = True
    r = simulate(m, Signals(entry, np.full((10, 1), 5.0)), 0, 10)
    t = r.trades.iloc[0]
    assert t["reason"] == "delisted" and t["exit"] == pytest.approx(98)


# ---------- Sentinel ----------
from lab.live import Sentinel

CFG = {"risk_per_trade": 0.005, "max_positions": 5, "min_notional": 5,
       "sentinel": {"daily_loss_limit": 0.03, "max_consecutive_losses": 3, "stale_feed_minutes": 30,
                    "max_price_deviation": 0.05}}


def _st(**kw):
    st = {"positions": {}, "day_start_equity": 500.0, "loss_streak": 0, "halted": None}
    st.update(kw)
    return st


def test_sentinel_order_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("lab.live.LEDGER", tmp_path / "l.jsonl")
    s = Sentinel(CFG, _st())
    good = {"price": 100, "qty": 0.5, "notional": 50, "stop_dist": 5}   # เสี่ยง 2.5 = 0.5% ของ 500
    assert s.review_order(good, 500, 100)[0]
    assert not s.review_order({**good, "qty": 1.0, "notional": 100}, 500, 100)[0]   # เสี่ยง 1%
    assert not s.review_order(good, 500, 90)[0]                                      # ราคาห่าง >5%
    assert not s.review_order({**good, "notional": 4, "qty": 0.04}, 500, 100)[0]     # ต่ำกว่า min
    assert not Sentinel(CFG, _st(positions={i: {} for i in range(5)})).review_order(good, 500, 100)[0]


def test_sentinel_halts(tmp_path, monkeypatch):
    monkeypatch.setattr("lab.live.LEDGER", tmp_path / "l.jsonl")
    st = _st()
    assert Sentinel(CFG, st).check_account(490)
    assert not Sentinel(CFG, st).check_account(484) and "daily loss" in st["halted"]["reason"]
    st2 = _st(loss_streak=3)
    assert not Sentinel(CFG, st2).check_account(500) and st2["halted"]


def test_sentinel_paper_pause_and_live_hard_stop(tmp_path, monkeypatch):
    monkeypatch.setattr("lab.live.LEDGER", tmp_path / "l.jsonl")
    st = _st(loss_streak=3)
    Sentinel({**CFG, "mode": "paper"}, st).check_account(500)
    assert st["halted"]["resume_on"]            # paper → กลับมาเองวันถัดไป
    st2 = _st(loss_streak=3)
    Sentinel({**CFG, "mode": "live"}, st2).check_account(500)
    assert st2["halted"]["resume_on"] is None   # live → ต้องให้เจ้าของปลด
