import pytest

from cryptoassist.alerts import AlertEngine, AlertRule
from cryptoassist.bot import BotSettings, TradingBot
from cryptoassist.exchange import Exchange
from cryptoassist.indicators import crossover, ema, rsi, sma
from cryptoassist.notifier import Notifier
from cryptoassist.portfolio import Portfolio


class FakeClient:
    """จำลอง ccxt exchange"""
    def __init__(self, closes):
        self.closes = list(closes)
        self.orders = []

    def fetch_ticker(self, symbol):
        return {"last": self.closes[-1], "percentage": (self.closes[-1] / self.closes[0] - 1) * 100}

    def fetch_ohlcv(self, symbol, timeframe="1h", limit=200):
        return [[i, c, c, c, c, 1] for i, c in enumerate(self.closes[-limit:])]

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.6f}"

    def create_order(self, symbol, type_, side, amount):
        o = {"amount": amount, "filled": amount, "average": self.closes[-1], "fee": {"cost": 0.05}}
        self.orders.append((side, o))
        return o


def fake_ex(closes):
    return Exchange("fake", client=FakeClient(closes))


# ---- indicators ----
def test_sma_ema():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    e = ema([1, 2, 3, 4, 5], 3)
    assert e[:2] == [None, None] and e[2] == 2 and e[3] == 3 and e[4] == 4


def test_rsi_bounds():
    assert rsi(list(range(1, 30)), 14)[-1] == 100
    assert rsi(list(range(30, 1, -1)), 14)[-1] == 0
    assert all(v is None for v in rsi([1, 2, 3], 14))


def test_crossover():
    assert crossover([1, 3], [2, 2]) == "golden"
    assert crossover([3, 1], [2, 2]) == "death"
    assert crossover([1, 1.5], [2, 2]) is None


# ---- portfolio ----
def test_portfolio_avg_cost(tmp_path):
    pf = Portfolio(str(tmp_path / "t.db"))
    pf.add_trade("btc/usdt", "buy", 1, 100)
    pf.add_trade("BTC/USDT", "buy", 1, 200, fee=2)
    p = pf.summary().positions["BTC/USDT"]
    assert p.amount == 2 and p.avg_cost == pytest.approx(151)
    pf.add_trade("BTC/USDT", "sell", 1, 251, fee=1)
    p = pf.summary().positions["BTC/USDT"]
    assert p.realized_pnl == pytest.approx(99)
    assert p.unrealized(161) == pytest.approx(10)
    with pytest.raises(ValueError):
        pf.add_trade("BTC/USDT", "sell", 5, 100)


# ---- alerts ----
def test_alert_fires_once_then_rearms():
    client = FakeClient([100] * 30)
    ex = Exchange("fake", client=client)
    n = Notifier()
    eng = AlertEngine([AlertRule("BTC/USDT", "price_above", 150)], ex, n)
    assert eng.check_once() == []
    client.closes.append(160)
    assert len(eng.check_once()) == 1
    assert eng.check_once() == []          # ไม่แจ้งซ้ำ
    client.closes.append(140)
    eng.check_once()                       # reset
    client.closes.append(170)
    assert len(eng.check_once()) == 1


def test_alert_rsi_and_validation():
    ex = fake_ex(list(range(100, 60, -1)))
    eng = AlertEngine([AlertRule("X/USDT", "rsi_below", 30)], ex, Notifier())
    assert len(eng.check_once()) == 1
    with pytest.raises(ValueError):
        AlertRule("X/USDT", "nope", 1)


# ---- bot ----
def make_bot(tmp_path, closes, live=False, **kw):
    s = BotSettings(symbol="BTC/USDT", fast=3, slow=6, rsi_period=5, rsi_buy_below=101,
                    order_quote_amount=100, paper_starting_quote=1000, poll_seconds=0, **kw)
    client = FakeClient(closes)
    return TradingBot(s, Exchange("fake", client=client), Portfolio(str(tmp_path / "b.db")), Notifier(), live=live), client


def test_bot_golden_cross_buys_then_take_profit(tmp_path):
    closes = [100 - i for i in range(20)] + [100]   # ลงยาวแล้วกระโดดขึ้น → golden cross
    bot, client = make_bot(tmp_path, closes)
    assert bot.step() == "buy"
    assert bot.position().amount == pytest.approx(99.9 / 100)
    assert bot.paper_cash() == pytest.approx(900)
    assert bot.step() == "hold"            # มีของแล้ว ไม่ซื้อเพิ่ม
    client.closes.append(110)              # +10% > TP 6%
    assert bot.step() == "sell"
    assert bot.position().amount == 0
    assert bot.paper_cash() > 1000


def test_bot_stop_loss(tmp_path):
    bot, client = make_bot(tmp_path, [100 - i for i in range(20)] + [100])
    bot.step()
    client.closes.append(95)               # -5% < SL 3%
    assert bot.step() == "sell"
    assert bot.paper_cash() < 1000


def test_bot_respects_max_position(tmp_path):
    bot, _ = make_bot(tmp_path, [100 - i for i in range(20)] + [100], max_position_quote=50)
    bot.step()
    assert bot.position() is None


def test_bot_live_sends_orders(tmp_path):
    bot, client = make_bot(tmp_path, [100 - i for i in range(20)] + [100], live=True)
    assert bot.step() == "buy"
    assert client.orders[0][0] == "buy"
    assert bot.pf.trades("live")[0]["fee"] == 0.05
