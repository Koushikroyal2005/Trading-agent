"""Market query service with durable HDD-backed observations."""
from backend.agents.data_agent import DataAgent


class MarketService:
    def __init__(self, data_agent: DataAgent, repository=None):
        self.data_agent = data_agent
        self.repository = repository

    async def quote(self, symbol: str) -> dict:
        snapshot = await self.data_agent.process({"symbol": symbol, "timeframe": 1})
        if self.repository: await self.repository.save_snapshot(snapshot, latest_only=True)
        bar = snapshot.bars[-1]
        return {"symbol": bar.symbol, "price": bar.close, "bid": round(bar.close-.01,2), "ask": round(bar.close+.01,2), "timestamp": bar.timestamp.isoformat(), "data_source": snapshot.source.value}

    async def history(self, symbol: str, days: int) -> dict:
        snapshot = await self.data_agent.process({"symbol": symbol, "timeframe": 60, "limit": min(days*7, 10_000)})
        if self.repository: await self.repository.save_snapshot(snapshot)
        limit = min(len(snapshot.bars), max(1, days)*7)
        return {"symbol": symbol, "bars": [bar.model_dump(mode="json") for bar in snapshot.bars[-limit:]], "indicators": snapshot.indicators, "regime": snapshot.regime, "data_source": snapshot.source.value}
