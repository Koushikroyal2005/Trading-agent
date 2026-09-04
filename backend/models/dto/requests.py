from pydantic import BaseModel, Field, model_validator

from backend.models.domain.entities import OrderType, Side


class OrderRequest(BaseModel):
    symbol: str
    side: Side
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    confirm_paper: bool = False

    @model_validator(mode="after")
    def validate_bracket(self):
        if (self.stop_loss is None) != (self.take_profit is None):
            raise ValueError("stop_loss and take_profit must be supplied together")
        if self.stop_loss is not None and self.side == Side.BUY and self.stop_loss >= self.take_profit:
            raise ValueError("buy bracket requires stop_loss below take_profit")
        if self.stop_loss is not None and self.side == Side.SELL and self.stop_loss <= self.take_profit:
            raise ValueError("sell bracket requires stop_loss above take_profit")
        return self


class StrategySelectionRequest(BaseModel):
    strategy: str


class CycleRequest(BaseModel):
    symbol: str = "AAPL"
    timeframe: int = Field(default=15, ge=1, le=60)
    execute: bool = False


class AutoTradeRequest(BaseModel):
    enabled: bool


class TradeFeedbackRequest(BaseModel):
    pnl: float
    sharpe: float = 0
    win_rate: float = Field(default=0.5, ge=0, le=1)
    drawdown: float = Field(default=0, ge=0)
