from fastapi.testclient import TestClient
from backend.api.main import agents,app,trading
from backend.storage.clients import SimulatedBrokerClient

# Tests must never call a real market-data or brokerage account from local .env.
test_broker=SimulatedBrokerClient()
agents["data"].market_client=None
agents["execution"].broker=test_broker
trading.broker=test_broker

def test_health_and_public_contract():
    with TestClient(app) as client:
        health=client.get("/health")
        assert health.status_code==200
        assert health.json()["mode"]=="PAPER_TRADING"
        quote=client.get("/api/v1/market/quotes",params={"symbol":"AAPL"})
        assert quote.status_code==200
        assert quote.json()["symbol"]=="AAPL"
        assert isinstance(quote.json()["timestamp"],str)
        history=client.get("/api/v1/market/history",params={"symbol":"AAPL","days":30})
        assert history.status_code==200
        assert len(history.json()["bars"]) >= 2
        statuses=client.get("/api/v1/agents/status")
        assert statuses.status_code==200
        assert len(statuses.json())==8

def test_manual_order_is_simulated_without_keys():
    with TestClient(app) as client:
        response=client.post("/api/v1/trade/order",json={"symbol":"AAPL","side":"buy","quantity":1,"order_type":"market","confirm_paper":True})
        assert response.status_code==200
        assert response.json()["broker_id"].startswith("sim-")
