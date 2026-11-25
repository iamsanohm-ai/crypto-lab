"""ไอเดียกลยุทธ์ของ Scout — ทุกข้อต้องอธิบายได้ในประโยคเดียวว่าทำไม edge ถึงมีอยู่และใครจ่ายให้.

แต่ละกลยุทธ์: build(m, **params) -> Signals และ GRID (ค่าพารามิเตอร์ที่ Judge ให้ลอง ≤ 9 ชุด)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab.engine import BARS_PER_DAY as D, Market, Signals


# ---------- helpers (ทุกตัวใช้ข้อมูลถึงแท่งปัจจุบันเท่านั้น) ----------
def _c(m): return m.df("close")
def ema(df, n): return df.ewm(span=n, adjust=False, min_periods=n).mean()
def sma(df, n): return df.rolling(n, min_periods=n).mean()


def atr(m: Market, n=14):
    h, l, c = m.df("high"), m.df("low"), m.df("close")
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()]).groupby(level=0).max().reindex(c.index)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(df, n=14):
    d = df.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def btc_regime(m: Market, n=200):
    """True ถ้า BTC อยู่เหนือ EMA ยาว (ตลาดขาขึ้น) — ใช้กรองทุกกลยุทธ์ที่เป็น long."""
    c = _c(m)["BTCUSDT"]
    up = (c > ema(c.to_frame(), n)["BTCUSDT"]).to_numpy()
    return np.repeat(up[:, None], len(m.symbols), axis=1)


def N(df): return df.to_numpy(dtype=float)
def B(df): return np.nan_to_num(df.to_numpy(dtype=float), nan=0).astype(bool) if not isinstance(df, np.ndarray) else df


# =====================================================================
# แต่ละไอเดีย: REASON = เหตุผลที่ edge มีอยู่ (ประโยคเดียว)
# =====================================================================
IDEAS: dict[str, dict] = {}


def idea(name, reason, grid, kills):
    def deco(fn):
        IDEAS[name] = {"fn": fn, "reason": reason, "grid": grid, "kills": kills}
        return fn
    return deco


@idea("donchian_breakout",
      "ราคาทะลุจุดสูงสุด N วันทำให้คนที่รอ breakout และคน short ที่ต้อง cover ไล่ซื้อตาม (trend follower ได้กำไรจากความช้าของคนอื่น)",
      [{"n": n, "stop": s} for n in (20 * D // 4 * 4 // 4, 10 * D, 20 * D) for s in (2.0, 3.0)][:6],
      "ตลาด sideways ที่ breakout หลอกบ่อย")
def donchian_breakout(m, n=60, stop=2.0, trail=3.0):
    c, h = _c(m), m.df("high")
    a = atr(m)
    entry = (c > h.rolling(n).max().shift(1)) & (c > ema(c, 200))
    return Signals(B(entry) & btc_regime(m), N(a * stop), trail_atr=N(a * trail), score=N(c.pct_change(n)))


@idea("squeeze_breakout",
      "ช่วงผันผวนต่ำสะสม stop order ไว้ทั้งสองฝั่ง พอราคาหลุดกรอบแคบจะเกิดแรงซื้อจาก stop/breakout order ซ้อนกัน",
      [{"q": q, "stop": s} for q in (0.1, 0.2) for s in (1.5, 2.5)],
      "ข่าวแรงที่ทำให้ราคาวิ่งสลับทิศทันที")
def squeeze_breakout(m, q=0.1, stop=2.0, look=20):
    c = _c(m)
    mid, sd = sma(c, look), c.rolling(look).std()
    bw = (4 * sd) / mid
    low_vol = bw <= bw.rolling(90 * D, min_periods=30 * D).quantile(q)
    entry = low_vol.shift(1, fill_value=False) & (c > mid + 2 * sd)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), target_r=3.0, trail_atr=N(a * 3), max_hold=30 * D)


@idea("trend_pullback",
      "ในเทรนด์ขาขึ้นแรง คนขายทำกำไรระยะสั้นทำให้ราคาย่อชั่วคราว แล้วเงินใหญ่ที่ตามเทรนด์กลับมาซื้อ",
      [{"rsi_lo": r, "stop": s} for r in (35, 45) for s in (1.5, 2.5)],
      "จุดกลับตัวของเทรนด์ — ย่อแล้วไม่เด้ง")
def trend_pullback(m, rsi_lo=40, stop=2.0):
    c = _c(m)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    r = rsi(c)
    dipped = (r.rolling(6).min() < rsi_lo)
    entry = (e50 > e200) & (c > e200) & dipped & (c > e20) & (c.shift(1) <= e20.shift(1))
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), target_r=2.5, max_hold=20 * D, exit=B(c < e50))


@idea("bb_mean_reversion_uptrend",
      "การเทขายตื่นตระหนกในเหรียญที่ยังเป็นขาขึ้นมักเกินจริง ผู้ซื้อช่วงลดราคารับของจากคนที่ถูกบังคับขาย",
      [{"k": k, "rsi_max": r} for k in (2.0, 2.5) for r in (25, 30)],
      "ตลาดหมีที่ราคาลงเป็นขั้นบันไดไม่มีเด้ง")
def bb_mean_reversion_uptrend(m, k=2.5, rsi_max=25, stop=2.0):
    c = _c(m)
    mid, sd = sma(c, 20), c.rolling(20).std()
    entry = (c < mid - k * sd) & (rsi(c) < rsi_max) & (c > ema(c, 200) * 0.9)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(c > mid), max_hold=10 * D)


@idea("bb_mean_reversion_any",
      "เหมือนข้างบนแต่ไม่กรองเทรนด์ — ทดสอบว่า edge มาจากการ overreaction จริงหรือแค่มาจากตลาดขาขึ้น",
      [{"k": k, "rsi_max": r} for k in (2.5, 3.0) for r in (20, 25)],
      "ตลาดหมีที่ราคาลงต่อเนื่อง")
def bb_mean_reversion_any(m, k=2.5, rsi_max=25, stop=2.0):
    c = _c(m)
    mid, sd = sma(c, 20), c.rolling(20).std()
    entry = (c < mid - k * sd) & (rsi(c) < rsi_max)
    a = atr(m)
    return Signals(B(entry), N(a * stop), exit=B(c > mid), max_hold=10 * D)


@idea("rsi2_connors",
      "การลงแรงระยะสั้นมากในขาขึ้นระยะยาวเป็นการขายของคนอ่อนแอ ราคามักกลับสู่ค่าเฉลี่ยภายในไม่กี่แท่ง",
      [{"lvl": l, "stop": s} for l in (5, 10) for s in (2.0, 3.0)],
      "crash ที่ลงต่อหลายวัน")
def rsi2_connors(m, lvl=5, stop=2.5):
    c = _c(m)
    entry = (rsi(c, 2) < lvl) & (c > sma(c, 200))
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(c > sma(c, 5)), max_hold=5 * D)


@idea("funding_negative_extreme",
      "funding ติดลบหนักแปลว่าคน short แออัดและต้องจ่ายค่าถือ เมื่อราคาไม่ลงต่อจะเกิด short squeeze",
      [{"z": z, "hold": h} for z in (-0.0002, -0.0005) for h in (3 * D, 7 * D)],
      "ข่าวร้ายจริงจังที่ทำให้ short ถูกต้อง (เช่น hack, delist)")
def funding_negative_extreme(m, z=-0.0003, hold=18, stop=3.0):
    c = _c(m)
    f = m.df("funding")
    entry = (f < z) & (c > c.shift(1))
    a = atr(m)
    return Signals(B(entry), N(a * stop), max_hold=hold, target_r=3.0)


@idea("breakout_funding_filter",
      "breakout ที่ funding ยังไม่ร้อน = คนยังไม่ใช้ leverage ไล่ราคา มีที่ว่างให้ขึ้นต่อ และไม่เสี่ยง long squeeze",
      [{"n": n, "fmax": f} for n in (10 * D, 20 * D) for f in (0.0001, 0.0003)],
      "ตลาด sideways / ช่วงที่ funding ไม่มีข้อมูล")
def breakout_funding_filter(m, n=60, fmax=0.0002, stop=2.0, trail=3.0):
    c, h = _c(m), m.df("high")
    f = m.df("funding").rolling(9).mean()
    a = atr(m)
    entry = (c > h.rolling(n).max().shift(1)) & (c > ema(c, 200)) & (f < fmax)
    return Signals(B(entry) & btc_regime(m), N(a * stop), trail_atr=N(a * trail), score=N(c.pct_change(n)))


@idea("volume_spike_momentum",
      "volume พุ่งพร้อมแท่งเขียวปิดใกล้ high = มีผู้ซื้อรายใหญ่/ข่าวใหม่เข้ามา ราคามักไหลตามต่อเพราะข้อมูลกระจายช้า",
      [{"mult": x, "stop": s} for x in (3, 5) for s in (1.5, 2.5)],
      "pump & dump ในเหรียญเล็ก")
def volume_spike_momentum(m, mult=3, stop=2.0):
    c, h, l, v = _c(m), m.df("high"), m.df("low"), m.df("qvol")
    pos_in_bar = (c - l) / (h - l).replace(0, np.nan)
    entry = (v > mult * v.rolling(30 * D // 5).mean().shift(1)) & (pos_in_bar > 0.75) & (c > c.shift(1) * 1.02)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), trail_atr=N(a * 3), max_hold=10 * D)


@idea("capitulation_reversal",
      "แท่งแดงยาวพร้อม volume มหาศาล = liquidation cascade ผู้ถูกบังคับขายขายต่ำกว่ามูลค่า แล้วราคาเด้งกลับ (ใช้แทนข้อมูล liquidation ที่ไม่มีให้ฟรี)",
      [{"mult": x, "drop": d} for x in (3, 5) for d in (0.05, 0.08)],
      "ข่าวร้ายระดับเปลี่ยนเกม (โปรเจกต์ล่ม)")
def capitulation_reversal(m, mult=4, drop=0.06, stop=1.5):
    c, o, v = _c(m), m.df("open"), m.df("qvol")
    entry = (v > mult * v.rolling(30).mean().shift(1)) & (c < o * (1 - drop))
    a = atr(m)
    return Signals(B(entry), N(a * stop), target_r=2.0, max_hold=3 * D)


@idea("btc_lead_lag",
      "เงินไหลเข้า BTC ก่อนแล้วค่อยกระจายไป altcoin — alt ที่ยังไม่ขยับตาม BTC จะไล่ตามภายหลัง",
      [{"btc_move": b, "hold": h} for b in (0.03, 0.05) for h in (2 * D, 4 * D)],
      "ช่วงที่ BTC dominance พุ่งและ alt ถูกขายทำกำไร")
def btc_lead_lag(m, btc_move=0.03, hold=12, lag_max=0.01, stop=2.0):
    c = _c(m)
    btc = c["BTCUSDT"].pct_change(2)
    alt = c.pct_change(2)
    entry = (alt < lag_max).mul(btc > btc_move, axis=0) & (c > ema(c, 50))
    entry["BTCUSDT"] = False
    a = atr(m)
    return Signals(B(entry), N(a * stop), max_hold=hold, score=N(-alt))


@idea("xs_momentum_rotation",
      "เหรียญที่แข็งที่สุดมักแข็งต่อ (momentum) เพราะนักลงทุนรายย่อยไล่ตามผลตอบแทนอดีตอย่างช้าๆ",
      [{"look": lk, "top": t} for lk in (14 * D, 30 * D) for t in (3, 5)],
      "จุดกลับตัวของตลาด (momentum crash)")
def xs_momentum_rotation(m, look=180, top=3, stop=3.0):
    c = _c(m)
    mom = c.pct_change(look).where(m.df("member"))
    rank = mom.rank(axis=1, ascending=False)
    weekly = pd.Series(np.arange(len(c)) % (7 * D) == 0, index=c.index)
    entry = (rank <= top).mul(weekly, axis=0) & (mom > 0)
    exit_ = (rank > top + 2).mul(weekly, axis=0) | (mom <= 0)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(exit_) | ~btc_regime(m), score=N(mom),
                   trail_atr=N(a * 5))


@idea("ts_momentum",
      "ผลตอบแทนย้อนหลัง 1 เดือนเป็นบวก + BTC ขาขึ้น = อยู่ฝั่งเดียวกับเงินไหลเข้า (time-series momentum)",
      [{"look": lk, "stop": s} for lk in (14 * D, 30 * D) for s in (3.0, 4.0)],
      "ตลาด chop ที่สัญญาณกลับไปกลับมา")
def ts_momentum(m, look=180, stop=3.0):
    c = _c(m)
    mom = c.pct_change(look)
    entry = (mom > 0) & (mom.shift(1) <= 0)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(mom < 0) | ~btc_regime(m), trail_atr=N(a * stop * 1.5))


@idea("ema_9_21_cross",
      "baseline: กลยุทธ์ที่บอทตัวแรกใช้อยู่ (EMA9/21 + RSI<70) — ต้องพิสูจน์ว่ามี edge จริงหรือไม่",
      [{"fast": f, "slow": s} for f, s in ((9, 21), (12, 26), (20, 50))],
      "ตลาด sideways")
def ema_9_21_cross(m, fast=9, slow=21):
    c = _c(m)
    ef, es = ema(c, fast), ema(c, slow)
    entry = (ef > es) & (ef.shift(1) <= es.shift(1)) & (rsi(c) < 70)
    exit_ = (ef < es)
    a = atr(m)
    return Signals(B(entry), N(a * 2), exit=B(exit_), target_r=2.0)


@idea("golden_cross_50_200",
      "trend ระยะยาวเปลี่ยนทิศ สถาบันที่ใช้ MA ยาวทยอยเข้าซื้อตาม",
      [{"fast": f, "slow": s} for f, s in ((50, 200), (30, 120))],
      "ตลาดที่เปลี่ยนทิศเร็ว (สัญญาณมาช้าเกินไป)")
def golden_cross(m, fast=50, slow=200):
    c = _c(m)
    ef, es = ema(c, fast), ema(c, slow)
    entry = (ef > es) & (ef.shift(1) <= es.shift(1))
    a = atr(m)
    return Signals(B(entry), N(a * 4), exit=B(ef < es), trail_atr=N(a * 6))


@idea("nr7_breakout",
      "แท่งที่แคบที่สุดใน 7 แท่ง = ตลาดลังเล ทิศทางที่หลุดออกมักมีแรงตามเพราะ stop ถูกกระตุ้น",
      [{"stop": s, "tr": t} for s in (1.0, 1.5) for t in (2.0, 3.0)],
      "ตลาดผันผวนสูงที่กรอบแคบไม่มีความหมาย")
def nr7_breakout(m, stop=1.0, tr=2.0):
    c, h, l = _c(m), m.df("high"), m.df("low")
    rng = h - l
    nr7 = rng <= rng.rolling(7).min()
    entry = nr7.shift(1, fill_value=False) & (c > h.shift(1)) & (c > ema(c, 100))
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), target_r=tr, max_hold=5 * D)


@idea("keltner_trend",
      "ราคาปิดนอก Keltner channel บน = แรงซื้อเกินความผันผวนปกติ ซึ่งมักเริ่มเทรนด์ใหม่",
      [{"k": k, "stop": s} for k in (1.5, 2.0) for s in (2.0, 3.0)],
      "ตลาด chop")
def keltner_trend(m, k=2.0, stop=2.0):
    c = _c(m)
    a = atr(m, 20)
    mid = ema(c, 20)
    entry = (c > mid + k * a) & (c.shift(1) <= mid.shift(1) + k * a.shift(1)) & (c > ema(c, 200))
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(c < mid), trail_atr=N(a * 3))


@idea("relative_strength_vs_btc",
      "alt ที่ทำ high ใหม่เทียบกับ BTC ขณะที่ BTC ขาขึ้น = มีเงินเฉพาะเจาะจงไหลเข้า (narrative/ข่าว)",
      [{"n": n, "stop": s} for n in (10 * D, 20 * D) for s in (2.0, 3.0)],
      "alt season จบ เงินไหลกลับ BTC")
def relative_strength_vs_btc(m, n=60, stop=2.5):
    c = _c(m)
    ratio = c.div(c["BTCUSDT"], axis=0)
    entry = (ratio > ratio.rolling(n).max().shift(1)) & (c > ema(c, 50))
    entry["BTCUSDT"] = False
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), trail_atr=N(a * 3), score=N(ratio.pct_change(n)))


@idea("funding_reset_pullback",
      "เมื่อ funding กลับจากร้อนจัดสู่ปกติพร้อมราคาย่อ = leverage ส่วนเกินถูกล้างแล้ว ขาขึ้นเดินต่อได้สะอาดกว่า",
      [{"hot": h, "stop": s} for h in (0.0003, 0.0005) for s in (2.0, 3.0)],
      "ตลาดที่ funding ร้อนเพราะเป็นยอดดอย")
def funding_reset_pullback(m, hot=0.0003, stop=2.0):
    c = _c(m)
    f = m.df("funding")
    was_hot = f.rolling(7 * D).max() > hot
    entry = was_hot & (f < 0.0001) & (c > ema(c, 100)) & (c < ema(c, 20))
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), target_r=2.5, max_hold=10 * D)


@idea("taker_buy_pressure",
      "สัดส่วน taker buy สูงผิดปกติ = มีคนยอมจ่าย spread เพื่อซื้อทันที (ข้อมูลใหม่/คนรู้ก่อน) ราคามักไหลตาม",
      [{"thr": t, "stop": s} for t in (0.6, 0.65) for s in (1.5, 2.5)],
      "wash trading / ปั่น volume")
def taker_buy_pressure(m, thr=0.6, stop=2.0):
    c = _c(m)
    tq, qv = m.df("taker"), m.df("qvol")
    ratio = tq.rolling(6).sum() / qv.rolling(6).sum()
    entry = (ratio > thr) & (qv.rolling(6).sum() > qv.rolling(30 * D // 5).mean() * 6 * 1.5) & (c > ema(c, 50))
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), target_r=2.0, max_hold=5 * D)


@idea("vol_expansion_trend",
      "ความผันผวนเพิ่มขึ้นพร้อมราคาทำ high ใหม่ = เทรนด์มีแรงจริง (ไม่ใช่ breakout เงียบที่หลอก)",
      [{"n": n, "stop": s} for n in (10 * D, 20 * D) for s in (2.0, 3.0)],
      "blow-off top")
def vol_expansion_trend(m, n=60, stop=2.5):
    c, h = _c(m), m.df("high")
    a = atr(m)
    a_slow = a.rolling(30 * D).mean()
    entry = (c > h.rolling(n).max().shift(1)) & (a > a_slow) & (c > ema(c, 200))
    return Signals(B(entry) & btc_regime(m), N(a * stop), trail_atr=N(a * 3))


@idea("weekly_open_trend",
      "ราคายืนเหนือราคาเปิดสัปดาห์พร้อมเทรนด์รายวันขึ้น = ผู้เล่นรายสัปดาห์อยู่ฝั่งซื้อ (โครงสร้างตลาดง่ายๆ ไม่ต้อง fit)",
      [{"stop": s} for s in (2.0, 3.0)],
      "ตลาด chop")
def weekly_open_trend(m, stop=2.0):
    c = _c(m)
    wk_open = m.df("open").groupby(c.index.tz_localize(None).to_period("W")).transform("first")
    entry = (c > wk_open * 1.03) & (c.shift(1) <= wk_open * 1.03) & (ema(c, 6 * 20) < c)
    a = atr(m)
    return Signals(B(entry) & btc_regime(m), N(a * stop), exit=B(c < wk_open), max_hold=7 * D)


@idea("range_grid",
      "แบบ grid: ตอนตลาด sideways ราคาแกว่งในกรอบ ซื้อใกล้ขอบล่าง ขายกลางกรอบ — ได้เงินจากคนที่ไล่ซื้อแพง/ขายถูกในกรอบ (แต่ต้องมี stop ใต้กรอบ ไม่ใช่ grid ไม่จำกัดที่ขาดทุนไม่สิ้นสุด)",
      [{"days": d, "zone": z} for d in (10, 20) for z in (0.15, 0.25)],
      "ราคาหลุดกรอบลงแรง (trend ขาลงใหม่) — grid แบบไม่มี stop จะขาดทุนหนักที่สุดตรงนี้")
def range_grid(m, days=20, zone=0.2, stop=1.0):
    c, h, l = _c(m), m.df("high"), m.df("low")
    n = days * D
    hi, lo = h.rolling(n).max(), l.rolling(n).min()
    width = (hi - lo) / c
    a = atr(m)
    # ตลาด sideways: กรอบไม่กว้างเกินไป และ EMA50 แทบไม่เอียง
    e50 = ema(c, 50)
    flat = (e50.pct_change(5 * D).abs() < 0.03) & (width < 0.35)
    pos = (c - lo) / (hi - lo).replace(0, np.nan)
    entry = flat & (pos < zone)
    exit_ = pos > 0.5
    stop_dist = (c - lo) + stop * a  # stop ใต้ขอบล่างของกรอบ
    return Signals(B(entry), N(stop_dist), exit=B(exit_), max_hold=n)


# ---------------- กฎคลาสสิกจาก "Open-source trading bots" (ผลเดิมทดสอบบนหุ้นรายวัน 25 ปี) — ทดสอบซ้ำบนคริปโต ----------------
@idea("classic_sma_crossover",
      "กฎคลาสสิก: SMA50 ตัดขึ้น SMA200 = เทรนด์ระยะยาวเปลี่ยนเป็นขาขึ้น (ทดสอบซ้ำจากไลบรารีบอทโอเพ่นซอร์สที่ใช้หุ้น 25 ปี)",
      [{"fast": 50, "slow": 200}], "ตลาดที่เปลี่ยนทิศเร็ว สัญญาณมาช้า")
def classic_sma_crossover(m, fast=50, slow=200):
    c = _c(m)
    f, s = sma(c, fast), sma(c, slow)
    return Signals(B((f > s) & (f.shift(1) <= s.shift(1))), N(c * 0.20), exit=B(f < s))


@idea("classic_rsi_reversion",
      "กฎคลาสสิก: RSI14 ลงต่ำกว่า 30 = ขายมากเกินไป ซื้อแล้วขายเมื่อ RSI เกิน 70 (ตัวที่ดีที่สุดในไลบรารีหุ้น +133%)",
      [{"lo": 30, "hi": 70}], "เทรนด์ขาลงที่ RSI ต่ำค้างนาน")
def classic_rsi_reversion(m, lo=30, hi=70):
    c = _c(m)
    r = rsi(c, 14)
    return Signals(B((r < lo) & (r.shift(1) >= lo)), N(c * 0.20), exit=B(r > hi))


@idea("classic_rsi_dip",
      "กฎคลาสสิก: ซื้อเมื่อ RSI14 < 30 ขณะราคาอยู่เหนือ SMA200 (ย่อในขาขึ้น) ขายเมื่อ RSI > 50",
      [{"lo": 30}], "ขาลงที่ทะลุ SMA200 ลงมา")
def classic_rsi_dip(m, lo=30):
    c = _c(m)
    r = rsi(c, 14)
    return Signals(B((r < lo) & (c > sma(c, 200))), N(c * 0.20), exit=B(r > 50))


@idea("classic_trend_pullback",
      "กฎคลาสสิก: ขาขึ้น (เหนือ SMA200) แล้วราคาย่อมาแตะ SMA50 และปิดกลับขึ้นไป = ซื้อตอนย่อ",
      [{"stop_pct": 0.10}], "จุดกลับตัวของเทรนด์")
def classic_trend_pullback(m, stop_pct=0.10):
    c = _c(m)
    s50 = sma(c, 50)
    return Signals(B((c > sma(c, 200)) & (m.df("low") <= s50) & (c > s50)), N(c * stop_pct), exit=B(c < sma(c, 200)))


@idea("classic_breakout",
      "กฎคลาสสิก: ปิดเหนือจุดสูงสุด 20 แท่ง = breakout ขายเมื่อหลุดจุดต่ำสุด 20 แท่ง (Turtle แบบย่อ)",
      [{"n": 20}], "ตลาด sideways ที่ breakout หลอก")
def classic_breakout(m, n=20):
    c = _c(m)
    return Signals(B(c > m.df("high").rolling(n).max().shift(1)), N(c * 0.10), exit=B(c < c.rolling(n).min().shift(1)))


@idea("classic_trend_stop5",
      "กฎคลาสสิก: ซื้อเมื่อราคาข้ามขึ้นเหนือ SMA200 ทุกสถานะมี stop-loss 5% ขายเมื่อหลุด SMA200",
      [{"stop_pct": 0.05}], "ความผันผวนสูง (stop 5% แคบเกินไปสำหรับคริปโต)")
def classic_trend_stop5(m, stop_pct=0.05):
    c = _c(m)
    s200 = sma(c, 200)
    return Signals(B((c > s200) & (c.shift(1) <= s200.shift(1))), N(c * stop_pct), exit=B(c < s200))
