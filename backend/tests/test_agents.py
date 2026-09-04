from pathlib import Path
import pytest
from backend.agents.factory import AgentFactory
from backend.infrastructure.event_bus import EventBus
from backend.services.orchestrator import TradingOrchestrator
from backend.services.portfolio_service import PortfolioService
from backend.storage.clients import GeminiReasoningClient,SimulatedBrokerClient
from backend.storage.repositories import TradingRepository
from backend.strategies import default_registry
from backend.utils.config import Settings

class EmptyMarketClient:
    async def history(self,symbol,timeframe,limit):return []

@pytest.mark.asyncio
async def test_data_agent_falls_back_when_market_is_closed():
    from backend.agents.data_agent import DataAgent
    agent=DataAgent(event_bus=EventBus(),market_client=EmptyMarketClient());await agent.initialize();snapshot=await agent.process({"symbol":"AAPL","timeframe":15})
    assert len(snapshot.bars)==100

@pytest.mark.asyncio
async def test_complete_agent_pipeline(tmp_path:Path):
    settings=Settings(database_url=f"sqlite+aiosqlite:///{tmp_path/'test.db'}",hdd_storage_path=tmp_path,redis_url="redis://localhost:6379/0")
    bus=EventBus();events=[]
    async def capture(event):events.append(event.topic)
    bus.subscribe("*",capture);repository=TradingRepository(settings.database_url);await repository.initialize();registry=default_registry();agents=AgentFactory(bus,settings,repository,SimulatedBrokerClient(),GeminiReasoningClient(None),registry).create_all();orchestrator=TradingOrchestrator(agents,bus,PortfolioService(),registry);await orchestrator.initialize();result=await orchestrator.run_cycle("AAPL",15)
    assert result["regime"] in {"bullish","bearish","ranging","volatile"}
    assert result["decision"]["strategy"] in registry.names()
    assert result["reasoning"]["provider"]=="local_fallback"
    assert "trading.cycle.completed" in events
    assert all(status["failures"]==0 for status in orchestrator.statuses())
    learned=await orchestrator.record_outcome(0.01,1.2,.6,.02)
    assert learned["updates"]==1 and learned["replay_size"]==1
    await repository.close()
