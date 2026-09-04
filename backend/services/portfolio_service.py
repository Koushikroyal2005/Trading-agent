"""Portfolio service backed by the configured paper broker."""
from backend.models.domain.entities import Portfolio


class PortfolioService:
    def __init__(self, broker=None) -> None:
        self.broker = broker
        self._portfolio = Portfolio()

    async def get(self, refresh: bool = True) -> Portfolio:
        if refresh and self.broker and hasattr(self.broker, "get_portfolio"):
            self._portfolio = await self.broker.get_portfolio()
        return self._portfolio.model_copy(deep=True)

    def update(self, portfolio: Portfolio) -> None:
        self._portfolio = portfolio
