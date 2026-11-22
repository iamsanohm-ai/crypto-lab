"""บอท paper trading + Sentinel — รันทุกชั่วโมง (scheduled task) ทำงานรอบเดียวแล้วจบ.

ลำดับ: โหลด state → Sentinel ตรวจ feed → จัดการสถานะที่ถือ (stop/target/trail/exit/time ด้วยแท่ง 1h ที่ผ่านมา)
      → ถ้ามีแท่ง 4h ปิดใหม่ คำนวณสัญญาณ → Sentinel ตรวจทุกออเดอร์ → จำลองการซื้อที่ราคาปัจจุบัน + ค่าธรรมเนียม
ทุกการตัดสินใจถูกเขียนลง ledger/decisions.jsonl (append-only) พร้อมเหตุผล
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from lab.data import API, ROOT, _get, candidate_symbols, klines, now_iso
from lab.engine import Costs, Market
from lab.strategies import IDEAS

LEDGER = ROOT / "ledger" / "decisions.jsonl"
CONFIG = ROOT / "config" / "strategy.yaml"
H4 = timedelta(hours=4)


CTX = {}


def log(event: str, **kw):
    LEDGER.parent.mkdir(exist_ok=True)
    rec = {"ts": now_iso(), **CTX, "event": event, **kw}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
    print(json.dumps(rec, default=str, ensure_ascii=False))


def state_path(name): return ROOT / "state" / f"paper_{name}.json"


def load_state(cfg, name) -> dict:
    if state_path(name).exists():
        return json.loads(state_path(name).read_text())
    return {"strategy": name, "cash": cfg["capital"], "positions": {}, "closed": [],
            "last_bar": None, "halted": None, "universe": {"month": None, "members": []},
            "day": None, "day_start_equity": cfg["capital"], "loss_streak": 0}


def save_state(st):
    state_path(st["strategy"]).parent.mkdir(exist_ok=True)
    state_path(st["strategy"]).write_text(json.dumps(st, indent=1, default=str))


def universe_for_month(month: str, top_n: int) -> list[str]:
    """กฎเดียวกับ backtest: top N ตาม quote volume ของเดือนก่อนหน้า."""
    prev_start = (pd.Timestamp(month + "-01", tz="UTC") - pd.offsets.MonthBegin(1))
    end = pd.Timestamp(month + "-01", tz="UTC")
    from concurrent.futures import ThreadPoolExecutor

    def one(s):
        raw = _get(f"{API}/klines?symbol={s}&interval=1M&startTime={int(prev_start.timestamp()*1000)}"
                   f"&endTime={int(end.timestamp()*1000)-1}&limit=1")
        k = json.loads(raw) if raw else []
        return s, (float(k[0][7]) if k else 0.0)

    with ThreadPoolExecutor(8) as pool:
        vols = dict(pool.map(one, candidate_symbols().query("status == 'TRADING'")["symbol"]))
    return [s for s, _ in sorted(vols.items(), key=lambda x: -x[1])[:top_n]]


def build_live_market(symbols: list[str], bars: int = 1000) -> Market:
    end = datetime.now(timezone.utc)
    start = end - H4 * bars
    from concurrent.futures import ThreadPoolExecutor
    end_ms = int(end.timestamp() * 1000)

    def one(s):
        k = klines(s, "4h", int(start.timestamp() * 1000), end_ms)
        return s, (k[k["close_time"] < end_ms].set_index("time") if len(k) else None)  # เฉพาะแท่งที่ปิดแล้ว

    with ThreadPoolExecutor(8) as pool:
        frames = {s: k for s, k in pool.map(one, sorted(set(symbols) | {"BTCUSDT"})) if k is not None}
        funds = dict(pool.map(lambda s: (s, funding_recent(s)), sorted(frames)))
    syms = sorted(frames)
    times = pd.DatetimeIndex(sorted(set().union(*[f.index for f in frames.values()])))
    mat = lambda col: pd.DataFrame({s: frames[s][col] for s in syms}).reindex(times).to_numpy(float)
    close = mat("close")
    fund = np.full_like(close, np.nan)
    for j, s in enumerate(syms):
        f = funds[s]
        if len(f):
            ct = pd.DataFrame({"t": (times + H4 - pd.Timedelta(milliseconds=1)).as_unit("ns")})
            f["t"] = f["t"].dt.as_unit("ns")
            fund[:, j] = pd.merge_asof(ct, f, on="t")["funding"].to_numpy()
    member = np.zeros_like(close, bool)
    for j, s in enumerate(syms):
        member[:, j] = s in symbols
    last_bar = np.array([np.max(np.where(~np.isnan(close[:, j]))[0]) for j in range(len(syms))])
    return Market(times, syms, mat("open"), mat("high"), mat("low"), close, mat("quote_volume"),
                  mat("taker_quote"), fund, member, last_bar)


def funding_recent(sym: str) -> pd.DataFrame:
    """funding ล่าสุด: ใช้ fapi ถ้าเข้าถึงได้ ไม่งั้น *ประมาณ* จาก premium index รายวันของ data.binance.vision
    ด้วยสูตร Binance  F = P + clamp(0.01% - P, -0.05%, +0.05%)  (ESTIMATE: ช้าได้ถึง ~32 ชม.)"""
    import io, zipfile
    try:
        raw = _get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=200", retries=1)
        d = json.loads(raw) if raw else None
        if isinstance(d, list) and d:
            return pd.DataFrame({"t": pd.to_datetime([x["fundingTime"] for x in d], unit="ms", utc=True),
                                 "funding": [float(x["fundingRate"]) for x in d], "estimated": False})
    except Exception:
        pass
    rows = []
    # ไฟล์รายเดือนล่าสุด (ค่าจริง) + premium index รายวันหลังจากนั้น (ค่าประมาณ)
    today = datetime.now(timezone.utc).date()
    first = today.replace(day=1)
    prev_month = (pd.Timestamp(first) - pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    raw = _get(f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{prev_month}.zip") if today.day <= 6 else None
    if raw:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for line in z.read(z.namelist()[0]).decode().splitlines()[1:]:
                p = line.split(",")
                rows.append((pd.Timestamp(int(p[0]), unit="ms", tz="UTC"), float(p[2]), False))
    for back in range(1, 6):  # กลยุทธ์ใช้ค่าเฉลี่ย 9 รอบ (3 วัน) → ย้อน 5 วันพอ
        d = today - timedelta(days=back)
        raw = _get(f"https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/{sym}/8h/{sym}-8h-{d}.zip")
        if not raw:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for line in z.read(z.namelist()[0]).decode().splitlines():
                p = line.split(",")
                if not p[0].isdigit():
                    continue
                prem = (float(p[1]) + float(p[4])) / 2
                est = prem + min(max(0.0001 - prem, -0.0005), 0.0005)
                rows.append((pd.Timestamp(int(p[6]) + 1, unit="ms", tz="UTC"), est, True))
    return pd.DataFrame(rows, columns=["t", "funding", "estimated"]).sort_values("t") if rows else pd.DataFrame()


def price_now(sym: str) -> float:
    return float(json.loads(_get(f"{API}/ticker/price?symbol={sym}"))["price"])


def recent_1h(sym: str, since: datetime) -> pd.DataFrame:
    k = klines(sym, "1h", int(since.timestamp() * 1000), int(datetime.now(timezone.utc).timestamp() * 1000))
    return k


class Sentinel:
    """ตรวจทุกออเดอร์ก่อนส่ง และหยุดระบบทันทีเมื่อเข้าเงื่อนไข."""

    def __init__(self, cfg, st):
        self.cfg, self.st = cfg, st

    def halt(self, reason):
        self.st["halted"] = {"at": now_iso(), "reason": reason}
        log("SENTINEL_HALT", reason=reason)

    def check_feed(self, m: Market) -> bool:
        age = datetime.now(timezone.utc) - (m.times[-1] + H4).to_pydatetime()
        if age > timedelta(minutes=self.cfg["sentinel"]["stale_feed_minutes"]) + H4:
            self.halt(f"stale feed: แท่งล่าสุดปิดเมื่อ {age} ที่แล้ว")
            return False
        return True

    def check_account(self, equity: float) -> bool:
        s = self.cfg["sentinel"]
        dd = equity / self.st["day_start_equity"] - 1
        if dd <= -s["daily_loss_limit"]:
            self.halt(f"daily loss {dd:.2%} ถึงเพดาน -{s['daily_loss_limit']:.0%}")
            return False
        if self.st["loss_streak"] >= s["max_consecutive_losses"]:
            self.halt(f"แพ้ติดกัน {self.st['loss_streak']} ครั้ง")
            return False
        return True

    def review_order(self, order: dict, equity: float, last_close: float) -> tuple[bool, str]:
        r = self.cfg
        if order["notional"] < r["min_notional"]:
            return False, "ต่ำกว่า min notional"
        risk_frac = order["qty"] * order["stop_dist"] / equity
        if risk_frac > r["risk_per_trade"] * 1.05:
            return False, f"ความเสี่ยง {risk_frac:.2%} เกิน {r['risk_per_trade']:.2%}"
        if abs(order["price"] / last_close - 1) > r["sentinel"]["max_price_deviation"]:
            return False, f"ราคาปัจจุบันห่างจากราคาปิดแท่งสัญญาณเกิน {r['sentinel']['max_price_deviation']:.0%}"
        if len(self.st["positions"]) >= r["max_positions"]:
            return False, "เต็มจำนวนสถานะสูงสุด"
        if not (0 < order["stop_dist"] < order["price"]):
            return False, "stop ผิดปกติ"
        return True, "ok"


def run_all(dry: bool = False):
    cfg = yaml.safe_load(CONFIG.read_text())
    cache = {}
    for strat in cfg["strategies"]:
        CTX.clear(); CTX.update({"strategy": strat["name"], "role": strat["role"], "mode": "paper"})
        try:
            run_once(cfg, strat, cache, dry)
        except Exception as e:  # สถานะของตัวอื่นต้องไม่พังตาม
            log("ERROR", error=repr(e))


def run_once(cfg, champ, cache, dry=False):
    st = load_state(cfg, champ["name"])
    if st.get("halted"):
        log("SKIP_HALTED", halted=st["halted"])
        return st
    costs = Costs(cfg["fee"], cfg["slippage"])
    c = costs.per_side
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    if st["universe"]["month"] != month:
        if ("uni", month) not in cache:
            cache[("uni", month)] = universe_for_month(month, cfg["universe_top_n"])
        st["universe"] = {"month": month, "members": cache[("uni", month)]}
        log("UNIVERSE", month=month, members=st["universe"]["members"])
    members = st["universe"]["members"]
    held = list(st["positions"])
    key = ("mkt", tuple(sorted(set(members) | set(held))))
    if key not in cache:
        cache[key] = build_live_market(list(key[1]))
    m = cache[key]
    sentinel = Sentinel(cfg, st)
    if not sentinel.check_feed(m):
        save_state(st); return st

    sig = IDEAS[champ["name"]]["fn"](m, **champ["params"])
    T = len(m.times) - 1  # แท่ง 4h ล่าสุดที่ปิดแล้ว
    last_bar_time = str(m.times[T])
    new_bar = st["last_bar"] != last_bar_time

    def close_position(sym, price, reason):
        p = st["positions"].pop(sym)
        proceeds = p["qty"] * price * (1 - c)
        pnl = proceeds - p["cost"]
        st["cash"] += proceeds
        st["loss_streak"] = st["loss_streak"] + 1 if pnl <= 0 else 0
        rec = {**p, "symbol": sym, "exit": price, "exit_time": now_iso(), "pnl": pnl, "reason": reason}
        st["closed"].append(rec)
        log("SELL", symbol=sym, price=price, pnl=round(pnl, 4), reason=reason)

    # ---- จัดการสถานะที่ถือ ----
    for sym in list(st["positions"]):
        p = st["positions"][sym]
        j = m.symbols.index(sym) if sym in m.symbols else None
        if j is None or np.isnan(m.close[T, j]):
            close_position(sym, p["last_price"] * (1 - costs.delist_haircut), "no data / delisted"); continue
        since = datetime.fromisoformat(p["checked_until"])
        h1 = recent_1h(sym, since)
        for _, bar in h1.iterrows():
            if bar["low"] <= p["stop"]:
                close_position(sym, min(bar["open"], p["stop"]), "stop"); break
            if p.get("target") and bar["high"] >= p["target"]:
                close_position(sym, max(bar["open"], p["target"]), "target"); break
        if sym not in st["positions"]:
            continue
        p["checked_until"] = now_iso()
        p["last_price"] = float(m.close[T, j])
        if new_bar:
            p["bars_held"] += 1
            if sig.exit is not None and sig.exit[T, j]:
                close_position(sym, price_now(sym), "signal exit"); continue
            if sig.max_hold and p["bars_held"] >= sig.max_hold:
                close_position(sym, price_now(sym), "time exit"); continue
            if sig.trail_atr is not None and sig.trail_atr[T, j] > 0:
                p["high_close"] = max(p["high_close"], float(m.close[T, j]))
                p["stop"] = max(p["stop"], p["high_close"] - float(sig.trail_atr[T, j]))

    # ---- ตรวจบัญชี ----
    equity = st["cash"] + sum(p["qty"] * p["last_price"] for p in st["positions"].values())
    today = now.strftime("%Y-%m-%d")
    if st["day"] != today:
        st["day"], st["day_start_equity"] = today, equity
    if not sentinel.check_account(equity):
        save_state(st); return st

    # ---- สัญญาณเข้าใหม่ (เฉพาะเมื่อมีแท่ง 4h ปิดใหม่) ----
    if new_bar:
        cand = [j for j in np.where(sig.entry[T] & m.member[T])[0] if m.symbols[j] not in st["positions"]]
        score = sig.score if sig.score is not None else np.nan_to_num(m.qvol)
        cand.sort(key=lambda j: -np.nan_to_num(score[T, j], nan=-np.inf))
        log("SIGNALS", bar=last_bar_time, candidates=[m.symbols[j] for j in cand])
        for j in cand:
            sym = m.symbols[j]
            if len(st["positions"]) >= cfg["max_positions"]:
                break
            px = price_now(sym)
            dist = float(sig.stop_dist[T, j])
            notional = min(equity * cfg["risk_per_trade"] / (dist / px), equity * cfg["max_position_frac"], st["cash"] / (1 + c))
            order = {"symbol": sym, "price": px, "qty": notional / px, "notional": notional, "stop_dist": dist}
            ok, why = sentinel.review_order(order, equity, float(m.close[T, j]))
            if not ok:
                log("SENTINEL_REJECT", **order, reason=why); continue
            if dry:
                log("DRY_BUY", **order); continue
            cost = notional * (1 + c)
            st["cash"] -= cost
            st["positions"][sym] = {"entry": px, "qty": order["qty"], "cost": cost, "stop": px - dist,
                                    "target": px + sig.target_r * dist if sig.target_r else None,
                                    "entry_time": now_iso(), "checked_until": now_iso(), "bars_held": 0,
                                    "high_close": px, "last_price": px, "signal_bar": last_bar_time}
            log("BUY", symbol=sym, price=px, qty=order["qty"], notional=round(notional, 2), stop=px - dist,
                reason=f"{champ['name']} entry on bar {last_bar_time}")
        st["last_bar"] = last_bar_time

    equity = st["cash"] + sum(p["qty"] * p["last_price"] for p in st["positions"].values())
    log("TICK", equity=round(equity, 2), cash=round(st["cash"], 2), positions=list(st["positions"]), new_bar=new_bar)
    save_state(st)
    return st


if __name__ == "__main__":
    run_all(dry="--dry" in sys.argv)
