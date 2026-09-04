"""REST and WebSocket composition root."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.factory import AgentFactory
from backend.api.websocket import WebSocketHub, websocket_loop
from backend.infrastructure.event_bus import EventBus
from backend.models.domain.entities import Order
from backend.models.dto.requests import AutoTradeRequest, CycleRequest, OrderRequest, StrategySelectionRequest, TradeFeedbackRequest
from backend.services.market_service import MarketService
from backend.services.orchestrator import TradingOrchestrator
from backend.services.portfolio_service import PortfolioService
from backend.services.system_state import SystemStateCaretaker
from backend.services.trading_service import TradingService
from backend.storage.clients import AlpacaBrokerClient, GeminiReasoningClient, SimulatedBrokerClient
from backend.storage.repositories import TradingRepository
from backend.strategies import default_registry
from backend.utils.config import get_settings
from backend.utils.logger import configure_logging

settings = get_settings()
log = configure_logging()
bus = EventBus(settings.redis_url, settings.event_stream_max_length)
hub = WebSocketHub()
repository = TradingRepository(settings.database_url)
registry = default_registry()
broker = AlpacaBrokerClient(settings.alpaca_api_key.get_secret_value(), settings.alpaca_secret_key.get_secret_value(), settings.alpaca_base_url) if settings.alpaca_configured else SimulatedBrokerClient()
reasoning = GeminiReasoningClient(settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None, settings.gemini_model)
agents = AgentFactory(bus, settings, repository, broker, reasoning, registry).create_all()
portfolios = PortfolioService(broker)
orchestrator = TradingOrchestrator(agents, bus, portfolios, registry, repository, broker, SystemStateCaretaker(settings.hdd_storage_path), settings.market_data_max_age_minutes)
market = MarketService(agents["data"], repository)
trading = TradingService(broker, repository, bus)
request_windows: dict[str, deque] = defaultdict(deque)


async def persist_event(event):
    await repository.save_event(event, success=event.topic != "agent.error")


async def publish_market_stream():
    while True:
        for symbol in settings.symbols:
            try:
                await hub.broadcast("market", await market.quote(symbol))
            except Exception as error:
                log.warning("market_stream_error", symbol=symbol, error_type=type(error).__name__, error=repr(error))
        await asyncio.sleep(settings.market_stream_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await repository.initialize()
    await bus.initialize()
    bus.subscribe("*", persist_event)
    bus.subscribe("*", hub.event_handler)
    await orchestrator.initialize()
    market_task = asyncio.create_task(publish_market_stream())
    log.info("system_started", mode=settings.mode, alpaca=settings.alpaca_configured, gemini=settings.gemini_configured, auto_trade=orchestrator.auto_trade)
    yield
    market_task.cancel()
    await asyncio.gather(market_task, return_exceptions=True)
    await bus.close()
    await repository.close()


app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan, docs_url="/docs", redoc_url="/redoc")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


async def authenticate(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key.get_secret_value():
        raise HTTPException(401, "invalid API key")


@app.middleware("http")
async def timing(request, call_next):
    now = time.monotonic()
    client = request.client.host if request.client else "unknown"
    window = request_windows[client]
    while window and now-window[0] > 60: window.popleft()
    if len(window) >= 100:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
    window.append(now)
    started = now
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter()-started)*1000:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
async def health():
    disk = psutil.disk_usage(str(Path(settings.hdd_storage_path).resolve()))
    memory = psutil.virtual_memory()
    checks = await asyncio.gather(repository.health(), bus.health(), return_exceptions=True)
    database_up = checks[0] is True
    redis_up = checks[1] is True
    healthy = database_up and redis_up and disk.free > 1024**3 and memory.percent < 90
    return {"status": "healthy" if healthy else "degraded", "mode": settings.mode, "services": {"database": "up" if database_up else "down", "redis": "up" if redis_up else "down", "alpaca": "configured" if settings.alpaca_configured else "simulated", "gemini": "configured" if settings.gemini_configured else "local_fallback"}, "resources": {"disk_free_gb": round(disk.free/1024**3,2), "memory_percent": memory.percent, "cpu_percent": psutil.cpu_percent()}, "system": orchestrator.system_status()}


@app.get("/health/deep", dependencies=[Depends(authenticate)])
async def deep_health():
    database, redis, alpaca, gemini = await asyncio.gather(repository.health(), bus.health(), broker.health(), reasoning.health() if settings.gemini_configured else asyncio.sleep(0, result=False), return_exceptions=True)
    services = {"database": database is True, "redis": redis is True, "alpaca": alpaca is True, "gemini": gemini is True if settings.gemini_configured else "local_fallback"}
    return {"status": "healthy" if all(value is True or value == "local_fallback" for value in services.values()) else "degraded", "services": services}


@app.get("/api/v1/market/quotes", dependencies=[Depends(authenticate)])
async def quote(symbol: str = Query("AAPL", min_length=1, max_length=10)): return await market.quote(symbol)


@app.get("/api/v1/market/history", dependencies=[Depends(authenticate)])
async def history(symbol: str = "AAPL", days: int = Query(30, ge=1, le=365)): return await market.history(symbol, days)


@app.post("/api/v1/trade/order", dependencies=[Depends(authenticate)])
async def place_order(request: OrderRequest):
    if orchestrator.emergency_stopped: raise HTTPException(409, "emergency stop is active")
    if not request.confirm_paper: raise HTTPException(400, "confirm_paper=true is required")
    values=request.model_dump(exclude={"confirm_paper"})
    return await trading.place(Order(**values))


@app.delete("/api/v1/trade/order/{order_id}", dependencies=[Depends(authenticate)])
async def cancel_order(order_id: str):
    if not await trading.cancel(order_id): raise HTTPException(404, "order not found")
    return {"cancelled": True, "order_id": order_id}


@app.get("/api/v1/trade/orders", dependencies=[Depends(authenticate)])
async def orders(limit: int = Query(100, ge=1, le=500)): return await repository.list_orders(limit)


@app.get("/api/v1/portfolio", dependencies=[Depends(authenticate)])
async def portfolio(): return await portfolios.get()


@app.get("/api/v1/performance", dependencies=[Depends(authenticate)])
async def performance(): return await repository.performance()


@app.get("/api/v1/data/stats", dependencies=[Depends(authenticate)])
async def data_stats(): return await repository.stats()


@app.get("/api/v1/agents/status", dependencies=[Depends(authenticate)])
async def agent_status(): return orchestrator.statuses()


@app.get("/api/v1/orchestrator/status", dependencies=[Depends(authenticate)])
async def orchestrator_status(): return orchestrator.system_status()


@app.post("/api/v1/agents/strategy/select", dependencies=[Depends(authenticate)])
async def select_strategy(request: StrategySelectionRequest):
    try: agents["strategy"].select(request.strategy); orchestrator._save_state()
    except KeyError as error: raise HTTPException(400, str(error)) from error
    return {"selected": agents["strategy"].selected, "available": registry.names()}


@app.get("/api/v1/backtest", dependencies=[Depends(authenticate)])
async def backtest(strategy: str = "momentum", days: int = Query(90, ge=30, le=365), symbol: str = "AAPL"):
    try: return await orchestrator.backtest(strategy, symbol, days)
    except KeyError as error: raise HTTPException(400, str(error)) from error


@app.post("/api/v1/orchestrator/run", dependencies=[Depends(authenticate)])
async def run_cycle(request: CycleRequest):
    try: return await orchestrator.run_cycle(request.symbol, request.timeframe, request.execute)
    except RuntimeError as error: raise HTTPException(409, str(error)) from error


@app.post("/api/v1/orchestrator/scheduled-run", dependencies=[Depends(authenticate)])
async def scheduled_run(request: CycleRequest):
    try: return await orchestrator.run_cycle(request.symbol, request.timeframe, execute=True)
    except RuntimeError as error: raise HTTPException(409, str(error)) from error


@app.post("/api/v1/orchestrator/reconcile", dependencies=[Depends(authenticate)])
async def reconcile(): return await orchestrator.reconcile()


@app.post("/api/v1/orchestrator/feedback", dependencies=[Depends(authenticate)])
async def trade_feedback(request: TradeFeedbackRequest):
    try: return await orchestrator.record_outcome(**request.model_dump())
    except RuntimeError as error: raise HTTPException(409, str(error)) from error


@app.post("/api/v1/orchestrator/auto-trade", dependencies=[Depends(authenticate)])
async def auto_trade(request: AutoTradeRequest):
    try: orchestrator.set_auto_trade(request.enabled)
    except RuntimeError as error: raise HTTPException(409, str(error)) from error
    return orchestrator.system_status()


@app.post("/api/v1/orchestrator/emergency-stop", dependencies=[Depends(authenticate)])
async def emergency_stop():
    cancelled = await orchestrator.emergency_stop()
    return {**orchestrator.system_status(), "cancelled_orders": cancelled}


@app.post("/api/v1/orchestrator/resume", dependencies=[Depends(authenticate)])
async def resume(): orchestrator.resume(); return orchestrator.system_status()


@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str, api_key: str | None = None):
    if settings.api_key and api_key != settings.api_key.get_secret_value(): await websocket.close(code=1008); return
    if channel not in {"market", "orders", "agents", "alerts", "performance"}: await websocket.close(code=1008); return
    await websocket_loop(hub, channel, websocket)
