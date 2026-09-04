"""Async persistence adapter for SQLite locally and TimescaleDB in Docker."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.models.domain.entities import AgentEvent, MarketSnapshot, Order
from backend.utils.risk_metrics import max_drawdown, sharpe_ratio


class Base(DeclarativeBase):
    pass


class OrderRecord(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    broker_id: Mapped[str | None] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(10), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), index=True)
    filled_price: Mapped[float | None] = mapped_column(Float)
    strategy: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(Text)


class EventRecord(Base):
    __tablename__ = "agent_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[str] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True)


class MarketDataRecord(Base):
    __tablename__ = "market_data"
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    vwap: Mapped[float | None] = mapped_column(Float)
    trade_count: Mapped[int] = mapped_column(Integer)


class IndicatorRecord(Base):
    __tablename__ = "indicator_values"
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    values: Mapped[dict] = mapped_column(JSON)


class TradingRepository:
    def __init__(self, database_url: str):
        if database_url.startswith("sqlite"):
            path = database_url.rsplit("///", 1)[-1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            if self.engine.url.drivername.startswith("sqlite"):
                await connection.execute(text("PRAGMA journal_mode=WAL"))
            await connection.run_sync(Base.metadata.create_all)

    async def health(self) -> bool:
        async with self.engine.connect() as connection:
            return (await connection.execute(text("SELECT 1"))).scalar_one() == 1

    async def save_order(self, order: Order) -> None:
        async with self.sessions() as session:
            record = OrderRecord(id=str(order.id), broker_id=order.broker_id, symbol=order.symbol, side=order.side.value, quantity=order.quantity, order_type=order.order_type.value, status=order.status, filled_price=order.filled_price, strategy=order.strategy, payload=order.model_dump_json())
            await session.merge(record)
            await session.commit()

    async def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            result = await session.execute(select(OrderRecord).limit(limit))
            orders = [json.loads(row.payload) for row in result.scalars()]
            return sorted(orders, key=lambda item: item.get("submitted_at", ""), reverse=True)

    async def save_event(self, event: AgentEvent, success: bool = True) -> None:
        async with self.sessions() as session:
            session.add(EventRecord(topic=event.topic, source=event.source, payload=json.dumps(event.payload, default=str), success=success, timestamp=event.timestamp.isoformat()))
            await session.commit()

    async def save_snapshot(self, snapshot: MarketSnapshot, latest_only: bool = False) -> None:
        """Persist de-duplicated bars and the indicator set once per snapshot."""
        async with self.sessions() as session:
            for bar in snapshot.bars[-1:] if latest_only else snapshot.bars:
                await session.merge(MarketDataRecord(time=bar.timestamp, symbol=bar.symbol, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, vwap=bar.vwap, trade_count=bar.trade_count))
            await session.merge(IndicatorRecord(time=snapshot.fetched_at, symbol=snapshot.symbol, values=snapshot.indicators))
            await session.commit()

    async def stats(self) -> dict[str, int]:
        async with self.sessions() as session:
            result = {}
            for name, model in (("orders", OrderRecord), ("events", EventRecord), ("market_bars", MarketDataRecord), ("indicator_sets", IndicatorRecord)):
                result[name] = int((await session.execute(select(func.count()).select_from(model))).scalar_one())
            return result

    async def performance(self) -> dict[str, float | int]:
        orders = await self.list_orders(limit=5000)
        filled = [item for item in orders if item.get("status") == "filled" and item.get("filled_price") is not None]
        returns: list[float] = []
        positions: dict[str, dict[str, float]] = {}
        wins = 0
        pnl_total = 0.0
        for order in sorted(filled, key=lambda item: item.get("submitted_at", "")):
            symbol = order["symbol"]
            direction = 1.0 if order["side"] == "buy" else -1.0
            quantity, price = float(order["quantity"]), float(order["filled_price"])
            current = positions.get(symbol, {"quantity": 0.0, "price": 0.0})
            if current["quantity"] == 0 or current["quantity"] * direction > 0:
                total = abs(current["quantity"]) + quantity
                current["price"] = (current["price"]*abs(current["quantity"]) + price*quantity) / total
                current["quantity"] += direction*quantity
            else:
                closed = min(abs(current["quantity"]), quantity)
                pnl = (price-current["price"]) * closed * (1 if current["quantity"] > 0 else -1)
                pnl_total += pnl; returns.append(pnl/max(current["price"]*closed,1e-9)); wins += pnl > 0
                remaining = abs(current["quantity"])-quantity
                if remaining > 0: current["quantity"] = (1 if current["quantity"] > 0 else -1)*remaining
                elif remaining < 0: current = {"quantity": direction*abs(remaining), "price": price}
                else: current = {"quantity": 0.0, "price": 0.0}
            positions[symbol] = current
        equity = [1.0]
        for value in returns:
            equity.append(equity[-1] * (1 + value))
        return {"total_return": equity[-1]-1, "realized_pnl": pnl_total, "win_rate": wins/max(len(returns),1), "sharpe_ratio": sharpe_ratio(returns), "max_drawdown": max_drawdown(equity), "trade_count": len(filled), "closed_trades": len(returns)}

    async def close(self) -> None:
        await self.engine.dispose()
