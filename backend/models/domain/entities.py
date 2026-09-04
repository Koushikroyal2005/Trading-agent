"""Framework-independent business entities."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentState(str, Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"
    STOPPED = "stopped"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class MarketRegime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    VOLATILE = "volatile"


class MarketDataSource(str, Enum):
    ALPACA = "alpaca"
    SYNTHETIC = "synthetic"


class MarketBar(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=utc_now)
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    trade_count: int = 0

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalnum() or len(value) > 10:
            raise ValueError("invalid symbol")
        return value


class MarketSnapshot(BaseModel):
    symbol: str
    timeframe_minutes: int = Field(default=15, ge=1, le=60)
    bars: list[MarketBar]
    indicators: dict[str, float] = Field(default_factory=dict)
    regime: MarketRegime = MarketRegime.RANGING
    source: MarketDataSource = MarketDataSource.SYNTHETIC
    fetched_at: datetime = Field(default_factory=utc_now)

    @property
    def is_tradable(self) -> bool:
        return self.source == MarketDataSource.ALPACA and bool(self.bars)


class TradeSignal(BaseModel):
    symbol: str
    action: Side
    confidence: float = Field(ge=0, le=1)
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float = Field(default=0, ge=0)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(BaseModel):
    approved: bool
    reason: str
    quantity: float = Field(default=0, ge=0)
    risk_percentage: float = Field(default=0, ge=0)
    var_95: float = 0
    sharpe_ratio: float = 0


class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    broker_id: str | None = None
    symbol: str
    side: Side
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    status: str = "pending"
    submitted_at: datetime = Field(default_factory=utc_now)
    filled_price: float | None = None
    strategy: str = "manual"
    client_order_id: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    data_source: MarketDataSource | None = None


class Position(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.current_price - self.average_price)


class Portfolio(BaseModel):
    cash: float = 100_000
    equity: float = 100_000
    buying_power: float = 100_000
    daily_pnl: float = 0
    positions: list[Position] = Field(default_factory=list)


class AgentStatus(BaseModel):
    name: str
    state: AgentState
    processed: int = 0
    failures: int = 0
    last_error: str | None = None
    last_execution_ms: float = 0
    updated_at: datetime = Field(default_factory=utc_now)


class AgentEvent(BaseModel):
    topic: str
    source: str
    payload: dict[str, Any]
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
