"""ตัวห่อ ccxt ให้ใช้ง่าย รองรับทุก exchange ที่ ccxt รองรับ."""
from __future__ import annotations

from typing import Any

import ccxt

from .config import exchange_credentials


class Exchange:
    def __init__(self, exchange_id: str, sandbox: bool = False, with_keys: bool = False, client: Any = None):
        self.id = exchange_id
        if client is not None:  # สำหรับเทส
            self.client = client
            return
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"ไม่รู้จัก exchange '{exchange_id}' (ดูรายชื่อด้วย: crypto-assist exchanges)")
        params: dict[str, Any] = {"enableRateLimit": True}
        if with_keys:
            creds = exchange_credentials(exchange_id)
            if not creds:
                raise RuntimeError(
                    f"ไม่พบ API key: ตั้งค่า {exchange_id.upper()}_API_KEY และ {exchange_id.upper()}_SECRET ใน environment"
                )
            params.update(creds)
        self.client = getattr(ccxt, exchange_id)(params)
        if sandbox:
            self.client.set_sandbox_mode(True)

    def price(self, symbol: str) -> float:
        t = self.client.fetch_ticker(symbol)
        return float(t["last"])

    def ticker(self, symbol: str) -> dict:
        return self.client.fetch_ticker(symbol)

    def closes(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> list[float]:
        candles = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [float(c[4]) for c in candles]

    def balance(self) -> dict:
        return self.client.fetch_balance()

    def market_buy_quote(self, symbol: str, quote_amount: float) -> dict:
        """ซื้อแบบ market ด้วยจำนวนเงิน quote (เช่น 50 USDT)."""
        price = self.price(symbol)
        amount = float(self.client.amount_to_precision(symbol, quote_amount / price))
        return self.client.create_order(symbol, "market", "buy", amount)

    def market_sell(self, symbol: str, amount: float) -> dict:
        amount = float(self.client.amount_to_precision(symbol, amount))
        return self.client.create_order(symbol, "market", "sell", amount)
