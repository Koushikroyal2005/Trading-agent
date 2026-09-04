from datetime import timedelta
from pathlib import Path

import pytest

from backend.agents.factory import AgentFactory
from backend.infrastructure.event_bus import EventBus
from backend.models.domain.entities import MarketDataSource, Order, Side, utc_now
from backend.services.orchestrator import TradingOrchestrator
from backend.services.portfolio_service import PortfolioService
from backend.services.system_state import SystemStateCaretaker
from backend.storage.clients import AlpacaBrokerClient, GeminiReasoningClient, SimulatedBrokerClient
from backend.storage.clients.alpaca_client import alpaca_price, alpaca_timeframe
from backend.storage.repositories import TradingRepository
from backend.strategies import default_registry
from backend.utils.config import Settings


async def build_system(tmp_path: Path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path/'safety.db'}", hdd_storage_path=tmp_path, redis_url="", alpaca_api_key=None, alpaca_secret_key=None, gemini_api_key=None)
    bus = EventBus(); repository = TradingRepository(settings.database_url); await repository.initialize()
    broker = SimulatedBrokerClient(); registry = default_registry()
    agents = AgentFactory(bus, settings, repository, broker, GeminiReasoningClient(None), registry).create_all()
    orchestrator = TradingOrchestrator(agents, bus, PortfolioService(broker), registry, repository, broker, SystemStateCaretaker(tmp_path))
    await orchestrator.initialize()
    return orchestrator, repository, broker


@pytest.mark.asyncio
async def test_synthetic_data_is_persisted_but_never_executed(tmp_path: Path):
    orchestrator, repository, broker = await build_system(tmp_path)
    orchestrator.auto_trade = True
    result = await orchestrator.run_cycle("AAPL", 15, execute=True)
    assert result["data_source"] == MarketDataSource.SYNTHETIC.value
    assert result["execution"] == {"requested": True, "allowed": False, "reason": "synthetic data cannot be traded"}
    assert result["order"] is None and broker.orders == {}
    stats = await repository.stats()
    assert stats["market_bars"] == 100 and stats["indicator_sets"] == 1
    await repository.close()


@pytest.mark.asyncio
async def test_analysis_never_executes_even_when_auto_trade_is_enabled(tmp_path: Path):
    orchestrator, repository, broker = await build_system(tmp_path)
    orchestrator.auto_trade = True
    result = await orchestrator.run_cycle("MSFT", 15, execute=False)
    assert result["execution"]["reason"] == "analysis-only cycle"
    assert broker.orders == {}
    await repository.close()


@pytest.mark.asyncio
async def test_emergency_stop_is_durable_and_cancels_orders(tmp_path: Path):
    orchestrator, repository, broker = await build_system(tmp_path)
    broker.orders["open"] = Order(symbol="AAPL", side=Side.BUY, quantity=1, status="accepted")
    orchestrator.auto_trade = True
    assert await orchestrator.emergency_stop() == 1
    restored, second_repository, _ = await build_system(tmp_path)
    assert restored.emergency_stopped is True and restored.auto_trade is False and restored.running is False
    await repository.close(); await second_repository.close()


@pytest.mark.asyncio
async def test_auto_trade_rejects_simulated_broker(tmp_path: Path):
    orchestrator, repository, _ = await build_system(tmp_path)
    with pytest.raises(RuntimeError, match="verified Alpaca"):
        orchestrator.set_auto_trade(True)
    await repository.close()


@pytest.mark.asyncio
async def test_alpaca_submission_uses_idempotency_and_bracket_exits(monkeypatch):
    client = AlpacaBrokerClient("key", "secret")
    captured = {}
    async def fake_request(method, path, **kwargs):
        captured.update({"method": method, "path": path, "payload": kwargs["json"]})
        return {"id": "broker-1", "status": "accepted", "filled_avg_price": None}
    monkeypatch.setattr(client, "_request", fake_request)
    order = await client.submit_order(Order(symbol="AAPL", side=Side.BUY, quantity=5.0821, stop_loss=99.12345, take_profit=103.98765, data_source=MarketDataSource.ALPACA))
    assert order.client_order_id.startswith("vector-")
    assert order.quantity == 5
    assert captured["payload"]["qty"] == "5.0"
    assert captured["payload"]["order_class"] == "bracket"
    assert captured["payload"]["stop_loss"]["stop_price"] == "99.12"
    assert captured["payload"]["take_profit"]["limit_price"] == "103.99"


def test_alpaca_price_respects_minimum_price_variance():
    assert alpaca_price(321.90142857142854) == "321.90"
    assert alpaca_price(0.123456) == "0.1235"


def test_alpaca_timeframe_uses_hour_unit_for_sixty_minutes():
    assert alpaca_timeframe(1) == "1Min"
    assert alpaca_timeframe(15) == "15Min"
    assert alpaca_timeframe(60) == "1Hour"


@pytest.mark.asyncio
async def test_performance_pairs_long_and_short_round_trips(tmp_path: Path):
    repository = TradingRepository(f"sqlite+aiosqlite:///{tmp_path/'performance.db'}"); await repository.initialize()
    now = utc_now()
    orders = [
        Order(symbol="AAPL", side=Side.BUY, quantity=2, status="filled", filled_price=100, submitted_at=now),
        Order(symbol="AAPL", side=Side.SELL, quantity=2, status="filled", filled_price=110, submitted_at=now+timedelta(minutes=1)),
        Order(symbol="MSFT", side=Side.SELL, quantity=1, status="filled", filled_price=200, submitted_at=now+timedelta(minutes=2)),
        Order(symbol="MSFT", side=Side.BUY, quantity=1, status="filled", filled_price=190, submitted_at=now+timedelta(minutes=3)),
    ]
    for order in orders: await repository.save_order(order)
    result = await repository.performance()
    assert result["closed_trades"] == 2 and result["realized_pnl"] == 30
    await repository.close()
