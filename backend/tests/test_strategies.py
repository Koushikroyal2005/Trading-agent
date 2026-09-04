import pytest
from backend.agents.data_agent import DataAgent
from backend.infrastructure.event_bus import EventBus
from backend.models.domain.entities import Side
from backend.agents.strategy_agent import StrategyAgent
from backend.models.domain.entities import MarketRegime
from backend.strategies import default_registry

@pytest.mark.asyncio
async def test_all_strategies_are_substitutable():
    data=DataAgent(event_bus=EventBus());await data.initialize();snapshot=await data.process({"symbol":"AAPL","timeframe":15});registry=default_registry()
    assert len(registry.names())==5
    for name in registry.names():
        signal=registry.get(name).generate(snapshot)
        assert signal.action in Side
        assert 0<=signal.confidence<=1
        assert signal.stop_loss!=signal.take_profit

@pytest.mark.asyncio
async def test_model_strategy_label_is_normalized_to_registry_key():
    data=DataAgent(event_bus=EventBus());await data.initialize();snapshot=await data.process({"symbol":"AAPL","timeframe":15})
    snapshot.regime=MarketRegime.RANGING;registry=default_registry();agent=StrategyAgent(event_bus=EventBus(),registry=registry);await agent.initialize()
    signal=await agent.process({"snapshot":snapshot,"recommended_strategy":"Mean Reversion Buy"})
    assert signal.strategy=="mean_reversion"
