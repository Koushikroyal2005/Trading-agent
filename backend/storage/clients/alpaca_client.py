"""Paper-only broker adapters and account reconciliation gateways."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import uuid4

import httpx

from backend.infrastructure.circuit_breaker import CircuitBreaker
from backend.models.domain.entities import MarketBar, Order, Portfolio, Position


def alpaca_timeframe(minutes: int) -> str:
    """Translate the supported application intervals to Alpaca's wire format."""
    if not 1 <= minutes <= 60:
        raise ValueError("timeframe must be between 1 and 60 minutes")
    return "1Hour" if minutes == 60 else f"{minutes}Min"


class SimulatedBrokerClient:
    """Deterministic local adapter used only when Alpaca is not configured."""

    is_simulated = True

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.portfolio = Portfolio()

    async def submit_order(self, order: Order) -> Order:
        order.broker_id = f"sim-{uuid4()}"
        order.status = "filled"
        order.filled_price = order.limit_price
        order.client_order_id = order.client_order_id or f"vector-{order.id.hex[:32]}"
        self.orders[str(order.id)] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        for order in self.orders.values():
            if str(order.id) == order_id or order.broker_id == order_id:
                order.status = "cancelled"
                return True
        return False

    async def cancel_all_orders(self) -> int:
        cancelled = 0
        for order in self.orders.values():
            if order.status not in {"cancelled", "filled"}:
                order.status = "cancelled"; cancelled += 1
        return cancelled

    async def get_portfolio(self) -> Portfolio:
        return self.portfolio.model_copy(deep=True)

    async def get_clock(self) -> dict:
        return {"is_open": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def list_orders(self, status: str = "all", limit: int = 500) -> list[dict]:
        return [order.model_dump(mode="json") for order in list(self.orders.values())[-limit:]]

    async def health(self) -> bool:
        return True


class AlpacaBrokerClient:
    """Minimal Alpaca paper REST client; live-trading endpoints are rejected."""

    is_simulated = False

    def __init__(self, key: str, secret: str, base_url: str = "https://paper-api.alpaca.markets"):
        if "paper-api" not in base_url:
            raise ValueError("Only Alpaca paper trading is permitted")
        self.base_url = base_url.rstrip("/").removesuffix("/v2")
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.breaker = CircuitBreaker()

    async def _request(self, method: str, path: str, **kwargs) -> dict | list:
        async def operation():
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.request(method, f"{self.base_url}/v2/{path.lstrip('/')}" , headers=self.headers, **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {}
        return await self.breaker.call(operation)

    async def submit_order(self, order: Order) -> Order:
        order.client_order_id = order.client_order_id or f"vector-{order.id.hex[:32]}"
        payload = {"symbol": order.symbol, "qty": str(order.quantity), "side": order.side.value, "type": order.order_type.value, "time_in_force": "day", "client_order_id": order.client_order_id}
        if order.limit_price is not None: payload["limit_price"] = str(order.limit_price)
        if order.stop_price is not None: payload["stop_price"] = str(order.stop_price)
        if order.stop_loss is not None and order.take_profit is not None:
            payload.update({"order_class": "bracket", "take_profit": {"limit_price": str(order.take_profit)}, "stop_loss": {"stop_price": str(order.stop_loss)}})
        data = await self._request("POST", "orders", json=payload)
        order.broker_id = str(data["id"])
        order.status = str(data.get("status", "accepted"))
        order.filled_price = float(data["filled_avg_price"]) if data.get("filled_avg_price") else None
        return order

    async def cancel_order(self, order_id: str) -> bool:
        try:
            await self._request("DELETE", f"orders/{order_id}")
            return True
        except httpx.HTTPStatusError as error:
            return error.response.status_code == 404

    async def cancel_all_orders(self) -> int:
        data = await self._request("DELETE", "orders")
        return len(data) if isinstance(data, list) else 0

    async def get_portfolio(self) -> Portfolio:
        account = await self._request("GET", "account")
        raw_positions = await self._request("GET", "positions")
        positions = [Position(symbol=item["symbol"], quantity=float(item["qty"]), average_price=float(item["avg_entry_price"]), current_price=float(item["current_price"])) for item in raw_positions]
        equity = float(account["equity"])
        last_equity = float(account.get("last_equity") or equity)
        return Portfolio(cash=float(account["cash"]), equity=equity, buying_power=float(account["buying_power"]), daily_pnl=equity-last_equity, positions=positions)

    async def get_clock(self) -> dict:
        return dict(await self._request("GET", "clock"))

    async def list_orders(self, status: str = "all", limit: int = 500) -> list[dict]:
        return list(await self._request("GET", "orders", params={"status": status, "limit": min(limit, 500), "nested": "true"}))

    async def health(self) -> bool:
        await self._request("GET", "account")
        return True

    async def history(self, symbol: str, timeframe: int, limit: int = 100) -> list[MarketBar]:
        # Alpaca accepts minute timeframes only up to 59 minutes. Hourly bars
        # use the separate ``Hour`` unit (for example, ``1Hour``).
        # Supplying an explicit lookback is also important before the US market
        # opens: without it Alpaca can return an empty current-day result.
        requested_limit = min(limit, 10_000)
        trading_sessions = ceil(requested_limit * timeframe / 390)
        lookback_days = min(max(7, trading_sessions * 2 + 2), 3650)
        params = {
            "timeframe": alpaca_timeframe(timeframe),
            "limit": requested_limit,
            "start": (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat(),
            "adjustment": "raw",
            "feed": "iex",
            "sort": "desc",
        }
        async def operation():
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"https://data.alpaca.markets/v2/stocks/{symbol}/bars", headers=self.headers, params=params)
                response.raise_for_status()
                return response.json()
        payload = await self.breaker.call(operation)
        bars = [MarketBar(symbol=symbol, timestamp=bar["t"], open=bar["o"], high=bar["h"], low=bar["l"], close=bar["c"], volume=bar["v"], vwap=bar.get("vw"), trade_count=bar.get("n",0)) for bar in payload.get("bars") or []]
        return sorted(bars, key=lambda bar: bar.timestamp)
