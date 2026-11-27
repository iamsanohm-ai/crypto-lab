"""กันพังซ้ำ: เพิ่มกลยุทธ์ใหม่ที่ Judge ยังไม่เคยทดสอบ แล้วหน้าเว็บ/สรุปเช้า/รายงานสัปดาห์ต้องยังสร้างได้
(เหตุการณ์จริง 25–26 พ.ย. 2026: เพิ่ม keltner_bold แล้ว dashboard + morning brief + weekly พังด้วย KeyError) — ไม่ใช้เน็ต"""
import json

import yaml

import lab.brief as brief
import lab.dashboard as dash
from lab.data import ROOT
from lab.strategies import IDEAS


def cfg_with_unjudged():
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    cfg["strategies"].append({"role": "challenger_9", "name": "brand_new_untested", "params": {}})
    return cfg


def test_every_configured_strategy_exists():
    cfg = yaml.safe_load((ROOT / "config" / "strategy.yaml").read_text())
    assert [s["name"] for s in cfg["strategies"] if s["name"] not in IDEAS] == []


def test_dashboard_builds_with_unjudged_strategy(tmp_path, monkeypatch):
    cfg = cfg_with_unjudged()
    monkeypatch.setattr(dash.yaml, "safe_load", lambda _t: cfg)
    t0 = 1_767_225_600_000   # แท่ง 4h ปลอม 700 แท่ง (ไม่ต่อเน็ต)
    kl = [[t0 + i * 14_400_000, "100", "101", "99", str(100 + i % 7), "1", t0 + (i + 1) * 14_400_000 - 1, "1000", 1, "0", "0", "0"] for i in range(700)]
    monkeypatch.setattr(dash, "_get", lambda url, *a, **k: json.dumps(kl if "/klines" in url else []).encode())
    monkeypatch.setattr(dash, "OUT", tmp_path / "data.json"); monkeypatch.setattr(dash, "OUT_SITE", tmp_path / "site" / "data.json")
    (tmp_path / "site").mkdir()
    try:
        out = dash.build()
    except (KeyError, TypeError) as e:          # ข้อผิดพลาดชนิดเดียวกับที่เคยทำให้หน้าเว็บค้าง
        raise AssertionError(f"dashboard พังเมื่อมีกลยุทธ์ที่ยังไม่มีผล Judge: {e!r}")
    acc = [a for a in out["accounts"] if a["strategy"] == "brand_new_untested"]
    assert acc and acc[0]["bt_return_pct"] is None


def test_briefs_build_with_unjudged_strategy(monkeypatch):
    cfg = cfg_with_unjudged()
    monkeypatch.setattr(brief.yaml, "safe_load", lambda _t: cfg)
    assert "brand_new_untested" in brief.morning()
    assert "brand_new_untested" in brief.weekly()


def test_xs_sub_weights_long_strong_short_weak():
    import numpy as np
    from lab.xs_paper import sub_weights
    closes = {f"C{i}USDT": np.r_[np.ones(200), np.full(1, 1 + i / 100)] for i in range(10)}   # C9 แข็งสุด, C0 อ่อนสุด
    w = sub_weights(closes, 7, 3)
    assert w["C9USDT"] > 0 and w["C0USDT"] < 0 and abs(sum(w.values())) < 1e-9 and abs(sum(abs(x) for x in w.values()) - 1) < 1e-9


def test_probability_engine_and_learning(tmp_path, monkeypatch):
    import numpy as np
    import lab.prob as pb
    rng = np.random.default_rng(1)
    up = np.exp(np.cumsum(np.full(300, 0.004)))                     # ขึ้นสม่ำเสมอ
    r = pb.simulate(up, atr=up[-1] * 0.01, rng=rng)
    f = pb.simulate(up, atr=up[-1] * 0.01, rng=rng, demean=True)
    assert r["p_up7"] > 0.95 and 0.3 < f["p_up7"] < 0.7               # เทรนด์ต่อ vs ไม่มีเทรนด์
    assert r["long"]["ev_pct"] > r["short"]["ev_pct"]
    # เรียนรู้: ทำนาย 80% แต่เกิดจริง 30% → ครั้งต่อไปต้องลดความมั่นใจลง
    monkeypatch.setattr(pb, "PRED", tmp_path / "pred.jsonl")
    (tmp_path / "pred.jsonl").write_text("\n".join(json.dumps({"t": "2026-01-01T00:00:00+00:00", "sym": "X", "p": 0.8, "price": 1, "outcome": int(i < 30)}) for i in range(100)))
    cal = pb.calibration()
    assert cal["n"] == 100 and pb.calibrate(0.8, cal) < 0.6
