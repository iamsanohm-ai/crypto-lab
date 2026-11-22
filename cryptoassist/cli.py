"""Command-line interface: python -m cryptoassist <command> ..."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import ccxt
from rich.console import Console
from rich.table import Table

from .alerts import AlertEngine
from .bot import BotSettings, TradingBot
from .config import load_config
from .exchange import Exchange
from .notifier import Notifier
from .portfolio import Portfolio

console = Console()


def _exchange(cfg, args, with_keys=False) -> Exchange:
    ex_id = args.exchange or cfg["exchange"]["id"]
    return Exchange(ex_id, sandbox=cfg["exchange"].get("sandbox", False), with_keys=with_keys)


# ---------------- price ----------------
def cmd_price(cfg, args):
    ex = _exchange(cfg, args)
    symbols = args.symbols or cfg["watchlist"]
    while True:
        table = Table(title=f"{ex.id} — {datetime.now():%Y-%m-%d %H:%M:%S}")
        for col in ("Symbol", "Last", "24h %", "High", "Low", "Volume (quote)"):
            table.add_column(col, justify="right" if col != "Symbol" else "left")
        for s in symbols:
            try:
                t = ex.ticker(s)
                pct = t.get("percentage")
                color = "green" if (pct or 0) >= 0 else "red"
                table.add_row(s, f"{t['last']:,.6g}", f"[{color}]{pct:+.2f}%[/]" if pct is not None else "-",
                              f"{t.get('high') or 0:,.6g}", f"{t.get('low') or 0:,.6g}",
                              f"{t.get('quoteVolume') or 0:,.0f}")
            except Exception as e:
                table.add_row(s, f"[red]error: {e}[/]", "", "", "", "")
        console.print(table)
        if not args.watch:
            break
        time.sleep(args.watch)


# ---------------- alerts ----------------
def cmd_alerts(cfg, args):
    if not cfg["alerts"]:
        console.print("[yellow]ยังไม่มีกฎแจ้งเตือนใน config (หัวข้อ alerts:)[/]")
        return
    engine = AlertEngine.from_config(cfg["alerts"], _exchange(cfg, args), Notifier(cfg["notify"].get("telegram", False)))
    console.print(f"ตรวจ {len(engine.rules)} กฎ: " + "; ".join(r.describe() for r in engine.rules))
    while True:
        fired = engine.check_once()
        if not args.loop:
            if not fired:
                console.print("ไม่มีเงื่อนไขใดเข้า")
            break
        time.sleep(args.interval)


# ---------------- portfolio ----------------
def cmd_pf_add(cfg, args):
    pf = Portfolio(cfg["db_path"])
    tid = pf.add_trade(args.symbol, args.side, args.amount, args.price, args.fee,
                       account=args.account, exchange=args.exchange or cfg["exchange"]["id"], note=args.note)
    console.print(f"[green]บันทึกแล้ว #{tid}[/] {args.side} {args.amount} {args.symbol.upper()} @ {args.price}")


def cmd_pf_list(cfg, args):
    pf = Portfolio(cfg["db_path"])
    table = Table(title="ประวัติการซื้อขาย")
    for c in ("#", "เวลา", "บัญชี", "Symbol", "Side", "จำนวน", "ราคา", "ค่าธรรมเนียม", "หมายเหตุ"):
        table.add_column(c)
    for t in pf.trades(args.account, args.symbol):
        table.add_row(str(t["id"]), f"{datetime.fromtimestamp(t['ts']):%Y-%m-%d %H:%M}", t["account"], t["symbol"],
                      f"[{'green' if t['side'] == 'buy' else 'red'}]{t['side']}[/]", f"{t['amount']:.8g}",
                      f"{t['price']:,.8g}", f"{t['fee']:.4g}", t["note"] or "")
    console.print(table)


def cmd_pf_delete(cfg, args):
    ok = Portfolio(cfg["db_path"]).delete_trade(args.id)
    console.print("[green]ลบแล้ว[/]" if ok else "[red]ไม่พบรายการนี้[/]")


def cmd_pf_summary(cfg, args):
    pf = Portfolio(cfg["db_path"])
    summary = pf.summary(args.account)
    ex = None if args.no_prices else _exchange(cfg, args)
    table = Table(title=f"สรุปพอร์ต ({args.account or 'ทุกบัญชี'})")
    for c in ("Symbol", "ถืออยู่", "ต้นทุนเฉลี่ย", "ราคาปัจจุบัน", "มูลค่า", "กำไรยังไม่รับรู้", "กำไรรับรู้แล้ว"):
        table.add_column(c, justify="right" if c != "Symbol" else "left")
    tot_val = tot_unr = tot_real = 0.0
    for sym, p in sorted(summary.positions.items()):
        price = None
        if ex and p.amount > 0:
            try:
                price = ex.price(sym)
            except Exception as e:
                console.print(f"[yellow]ดึงราคา {sym} ไม่ได้: {e}[/]")
        unr = p.unrealized(price) if price else None
        val = p.amount * price if price else None
        tot_val += val or 0
        tot_unr += unr or 0
        tot_real += p.realized_pnl
        pct = f" ({unr / p.cost_basis * 100:+.2f}%)" if unr is not None and p.cost_basis else ""
        table.add_row(sym, f"{p.amount:.8g}", f"{p.avg_cost:,.6g}", f"{price:,.6g}" if price else "-",
                      f"{val:,.2f}" if val is not None else "-",
                      f"[{'green' if (unr or 0) >= 0 else 'red'}]{unr:+,.2f}{pct}[/]" if unr is not None else "-",
                      f"[{'green' if p.realized_pnl >= 0 else 'red'}]{p.realized_pnl:+,.2f}[/]")
    table.add_section()
    table.add_row("[bold]รวม", "", "", "", f"[bold]{tot_val:,.2f}", f"[bold]{tot_unr:+,.2f}", f"[bold]{tot_real:+,.2f}")
    console.print(table)
    if args.account == "paper":
        console.print(f"เงินสดจำลองคงเหลือ: {cfg['bot']['paper_starting_quote'] + summary.quote_flow:,.2f}")


# ---------------- bot ----------------
def cmd_bot(cfg, args):
    settings = BotSettings(**cfg["bot"])
    if args.symbol:
        settings.symbol = args.symbol
    if args.live:
        console.print("[bold red]⚠️  โหมด LIVE จะส่งคำสั่งซื้อขายด้วยเงินจริง[/]")
        console.print(f"   symbol={settings.symbol} ต่อออเดอร์={settings.order_quote_amount} เพดาน={settings.max_position_quote}")
        if input("พิมพ์ YES เพื่อยืนยัน: ").strip() != "YES":
            console.print("ยกเลิก")
            return
    ex = _exchange(cfg, args, with_keys=args.live)
    bot = TradingBot(settings, ex, Portfolio(cfg["db_path"]), Notifier(cfg["notify"].get("telegram", False)), live=args.live)
    try:
        bot.run(max_steps=args.steps)
    except KeyboardInterrupt:
        console.print("\nหยุดบอทแล้ว")


def cmd_exchanges(cfg, args):
    console.print(", ".join(ccxt.exchanges))
    console.print(f"\nรวม {len(ccxt.exchanges)} exchange")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cryptoassist", description="ผู้ช่วยเทรดคริปโต: ราคา แจ้งเตือน พอร์ต บอท")
    p.add_argument("-c", "--config", default="config.yaml", help="ไฟล์ config (default: config.yaml)")
    p.add_argument("-x", "--exchange", help="override exchange id เช่น binance, okx, bitkub, kraken")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("price", help="ดูราคา")
    sp.add_argument("symbols", nargs="*", help="เช่น BTC/USDT ETH/USDT (ว่าง = watchlist)")
    sp.add_argument("-w", "--watch", type=int, metavar="SEC", help="รีเฟรชทุก N วินาที")
    sp.set_defaults(func=cmd_price)

    sa = sub.add_parser("alerts", help="ตรวจกฎแจ้งเตือนจาก config")
    sa.add_argument("--loop", action="store_true", help="ทำงานต่อเนื่อง")
    sa.add_argument("--interval", type=int, default=60, help="วินาทีระหว่างรอบ (default 60)")
    sa.set_defaults(func=cmd_alerts)

    spf = sub.add_parser("portfolio", aliases=["pf"], help="จัดการพอร์ต")
    pfs = spf.add_subparsers(dest="pfcmd", required=True)
    a = pfs.add_parser("add", help="บันทึกการซื้อขาย")
    a.add_argument("side", choices=["buy", "sell"])
    a.add_argument("symbol")
    a.add_argument("amount", type=float)
    a.add_argument("price", type=float)
    a.add_argument("--fee", type=float, default=0.0, help="ค่าธรรมเนียม (หน่วย quote)")
    a.add_argument("--account", default="manual")
    a.add_argument("--note", default="")
    a.set_defaults(func=cmd_pf_add)
    l = pfs.add_parser("list", help="ดูประวัติ")
    l.add_argument("--account")
    l.add_argument("--symbol")
    l.set_defaults(func=cmd_pf_list)
    s = pfs.add_parser("summary", help="สรุปกำไร/ขาดทุน")
    s.add_argument("--account", help="manual / paper / live (ว่าง = ทั้งหมด)")
    s.add_argument("--no-prices", action="store_true", help="ไม่ดึงราคาปัจจุบัน")
    s.set_defaults(func=cmd_pf_summary)
    d = pfs.add_parser("delete", help="ลบรายการ")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_pf_delete)

    sb = sub.add_parser("bot", help="รันบอทเทรด (ค่าเริ่มต้น: paper trading)")
    sb.add_argument("--symbol")
    sb.add_argument("--live", action="store_true", help="ใช้เงินจริง (ต้องตั้ง API key ใน env)")
    sb.add_argument("--steps", type=int, help="จำนวนรอบ (ว่าง = ไม่จำกัด)")
    sb.set_defaults(func=cmd_bot)

    se = sub.add_parser("exchanges", help="รายชื่อ exchange ที่รองรับ")
    se.set_defaults(func=cmd_exchanges)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    try:
        args.func(cfg, args)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]ผิดพลาด: {e}[/]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
