# Vector Multi-Agent Paper Trading System

Vector is a paper-trading-only system for analyzing and trading 1-60 minute market intervals. It combines independent Python agents, five rule-based strategies, broker-backed risk controls, Gemini Flash summaries, scenario retrieval, outcome-driven reinforcement learning, TimescaleDB, Redis Streams, Celery, FastAPI, WebSockets, and a React dashboard.

The default scheduled symbols are:

- `AAPL`: Apple Inc.
- `MSFT`: Microsoft Corporation
- `SPY`: an ETF that tracks the S&P 500

> **Safety notice:** This project is for demonstration and paper trading. It is not financial advice. The broker adapter rejects non-paper Alpaca URLs. Synthetic data can be analyzed but can never pass the automatic execution gate.

## Contents

- [Capabilities](#capabilities)
- [Operating states](#operating-states)
- [Architecture](#architecture)
- [Agents](#agents)
- [LLD, patterns, and SOLID](#lld-patterns-and-solid)
- [Project structure](#project-structure)
- [Setup and configuration](#setup-and-configuration)
- [One-command startup](#one-command-startup)
- [Dashboard and automation](#dashboard-and-automation)
- [API reference](#api-reference)
- [HDD storage and backup](#hdd-storage-and-backup)
- [Testing and monitoring](#testing-and-monitoring)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

## Capabilities

- Eight bounded agents communicating through an event bus.
- Alpaca IEX history and Alpaca paper-account integration.
- Analysis of 1-60 minute bars; scheduled defaults use 15-minute bars.
- Momentum, mean-reversion, breakout, trend-following, and swing strategies.
- Risk checks for confidence, buying power, daily loss, position exposure, stop distance, Kelly sizing, VaR, and Sharpe ratio.
- Gemini Flash decision summaries with a deterministic local fallback.
- A compact 128-dimensional top-five scenario retrieval store.
- Lightweight online RL with optional Stable-Baselines3 PPO.
- Durable bars, indicators, events, orders, state, knowledge, and checkpoints.
- Redis Streams, distributed task locks, Celery worker, and Celery Beat.
- REST, OpenAPI, WebSockets, and a live React dashboard.
- Idempotent paper orders, bracket exits, reconciliation, and emergency stop.

## Operating states

These controls are different:

```text
Docker stack running
  -> API, UI, database, Redis, worker, and scheduler are available

Worker + scheduler running
  -> AAPL/MSFT/SPY analysis is requested every five minutes

Auto trade ON
  -> approved scheduled signals may submit Alpaca PAPER orders
```

```text
Worker/scheduler OFF + Auto trade OFF = manual analysis only
Worker/scheduler ON  + Auto trade OFF = automatic analysis, no orders
Worker/scheduler ON  + Auto trade ON  = automatic analysis and eligible paper orders
Emergency stop ON                    = cycles blocked and pending orders cancelled
```

Important behavior:

- **Run analysis** always sends `execute=false`; it never places an order.
- Enabling Auto trade does not immediately place an order. It permits future scheduled cycles to execute approved signals.
- Disabling Auto trade prevents new automatic orders but does not cancel orders or close positions.
- Emergency stop disables Auto trade, persists across restarts, blocks cycles, and cancels pending paper orders. It does not liquidate filled positions.
- Auto trade state persists across restarts. Always check it after startup.

## Architecture

### Deployment view

```mermaid
flowchart LR
    Browser[React dashboard<br/>localhost:3000]
    API[FastAPI API<br/>localhost:8000]
    Beat[Celery Beat<br/>scheduler]
    Worker[Celery worker]
    Redis[(Redis<br/>events, tasks, locks)]
    DB[(TimescaleDB)]
    Alpaca[Alpaca<br/>IEX + paper broker]
    Gemini[Gemini Flash]
    HDD[(HDD bind mounts)]

    Browser <-->|REST + WebSocket| API
    Beat -->|due tasks| Redis
    Redis -->|task queue| Worker
    Worker -->|internal REST| API
    API <-->|events| Redis
    API <-->|records| DB
    API <-->|market/account/orders| Alpaca
    API <-->|summary| Gemini
    Redis --- HDD
    DB --- HDD
    API --- HDD
```

The API owns the orchestrator. Celery tasks call internal REST endpoints instead of creating additional in-process orchestrators, so safety state has one authority.

### Decision sequence

```mermaid
sequenceDiagram
    participant B as Celery Beat
    participant W as Worker
    participant O as TradingOrchestrator
    participant D as DataAgent
    participant K as KnowledgeAgent
    participant C as CoTAgent
    participant S as StrategyAgent
    participant R as RiskAgent
    participant E as ExecutionAgent
    participant A as Alpaca Paper

    B->>W: trading.run_cycle(symbol, 15)
    W->>O: POST /scheduled-run
    O->>D: bars, indicators, provenance
    D->>A: request IEX history
    O->>K: retrieve similar scenarios
    O->>C: summarize and recommend strategy
    O->>S: generate BUY / SELL / HOLD
    O->>R: validate risk and size
    O->>O: apply execution gates
    alt every gate passes and Auto trade is ON
        O->>E: execute approved signal
        E->>A: idempotent bracket paper order
    else analysis or rejection
        O-->>W: order = null and reason
    end
```

### Execution gate

```mermaid
flowchart TD
    Start[Scheduled cycle requests execution] --> Auto{Auto trade ON?}
    Auto -- No --> Block[No order]
    Auto -- Yes --> Stop{Emergency stop inactive?}
    Stop -- No --> Block
    Stop -- Yes --> Source{Real Alpaca data?}
    Source -- No --> Block
    Source -- Yes --> Fresh{Latest bar fresh?}
    Fresh -- No --> Block
    Fresh -- Yes --> Paper{Alpaca paper broker?}
    Paper -- No --> Block
    Paper -- Yes --> Open{Market open?}
    Open -- No --> Block
    Open -- Yes --> Existing{Open order for symbol?}
    Existing -- Yes --> Block
    Existing -- No --> Risk{Risk approved?}
    Risk -- No --> Block
    Risk -- Yes --> Submit[Submit bracket paper order]
```

## Agents

### Data Agent

Fetches Alpaca bars, calculates indicators, classifies market regime, and records provenance. It can produce deterministic synthetic data when allowed and Alpaca is unavailable. Synthetic snapshots are visibly labeled and cannot be traded automatically.

### Knowledge Agent

Embeds indicators into 128 dimensions and returns the five most similar saved scenarios. The standard build uses HDD-friendly JSONL plus cosine similarity. Optional dependencies enable ChromaDB. The store begins empty and learns scenarios only from closed-trade outcomes or explicit feedback.

### CoT Agent

Sends concise market context to Gemini Flash and receives regime, recommended strategy, confidence, and a reasoning summary. Private model chain-of-thought is not requested or stored. Gemini failures and timeouts produce a clearly labeled local fallback.

### Strategy Agent

Selects one registered implementation:

- `momentum`: momentum, MACD, and RSI alignment.
- `mean_reversion`: Bollinger deviation with RSI confirmation.
- `breakout`: support/resistance breakout with volume.
- `trend_following`: fast/slow EMA alignment.
- `swing`: VWAP position with neutral RSI.

Every strategy emits a normalized `TradeSignal` containing BUY, SELL, or HOLD, confidence, entry, stop loss, take profit, and rationale.

### Risk Agent

Rejects HOLD, confidence below 55%, invalid account state, daily-loss violations, and exhausted exposure. Quantity is bounded by buying power, remaining per-symbol exposure, stop-distance risk, and capped Kelly sizing. Defaults are 5% maximum position exposure and 2% daily loss.

### Execution Agent

Creates an idempotent order only after risk and orchestration gates approve it. Stop-loss and take-profit values become Alpaca bracket legs.

### RL Agent

Produces a BUY/SELL/HOLD policy from a 128-dimensional state. The standard build uses a lightweight policy-gradient fallback; optional dependencies enable PPO. It learns from reconciled outcomes, not from every bar, and saves a compressed checkpoint after updates.

### Validation Agent

Backtests a strategy and reports evaluated bars, return, Sharpe ratio, drawdown, win rate, and data source.

## LLD, patterns, and SOLID

### Class relationships

```mermaid
classDiagram
    class BaseAgent {
        +initialize()
        +process(input)
        +validate(output)
        +get_status()
        #_process(input)
    }
    class DataAgent
    class KnowledgeAgent
    class CoTAgent
    class StrategyAgent
    class RiskAgent
    class ExecutionAgent
    class RLAgent
    class ValidationAgent
    class TradingOrchestrator {
        +run_cycle(symbol, timeframe, execute)
        +reconcile()
        +set_auto_trade(enabled)
        +emergency_stop()
    }
    class EventBus
    class StrategyRegistry
    class TradingRepository
    class AlpacaBrokerClient
    class GeminiReasoningClient
    class SystemStateCaretaker

    BaseAgent <|-- DataAgent
    BaseAgent <|-- KnowledgeAgent
    BaseAgent <|-- CoTAgent
    BaseAgent <|-- StrategyAgent
    BaseAgent <|-- RiskAgent
    BaseAgent <|-- ExecutionAgent
    BaseAgent <|-- RLAgent
    BaseAgent <|-- ValidationAgent
    TradingOrchestrator o-- BaseAgent
    TradingOrchestrator --> EventBus
    TradingOrchestrator --> StrategyRegistry
    TradingOrchestrator --> TradingRepository
    TradingOrchestrator --> AlpacaBrokerClient
    TradingOrchestrator --> SystemStateCaretaker
    CoTAgent --> GeminiReasoningClient
```

Design patterns:

- **Template Method:** `BaseAgent.process()` owns timeout, validation, status, error handling, and publication; subclasses implement `_process()`.
- **Strategy + Registry:** new strategies can be registered without changing the orchestrator.
- **Factory:** `AgentFactory` composes dependencies.
- **Observer / Pub-Sub:** `EventBus` delivers local events and appends a capped Redis Stream.
- **Repository:** `TradingRepository` isolates SQLite/TimescaleDB.
- **Adapter:** Alpaca, Gemini, simulated broker, Redis, and DB clients adapt external systems.
- **Command:** `PlaceOrderCommand` supports execution and cancellation.
- **Memento:** `SystemStateCaretaker` atomically saves/restores safety state.
- **Circuit Breaker:** repeated external failures temporarily open the circuit.
- **Orchestrator / Facade:** `TradingOrchestrator` coordinates the workflow and policy.

SOLID:

- **Single Responsibility:** acquisition, reasoning, strategy, risk, execution, persistence, and transport are separate.
- **Open/Closed:** strategies extend through the registry.
- **Liskov Substitution:** simulated and Alpaca brokers provide the behavior expected by services.
- **Interface Segregation:** components consume small task-specific methods.
- **Dependency Inversion:** the factory injects bus, repository, broker, reasoning, and registry dependencies.

## Project structure

```text
trading-system/
|-- backend/
|   |-- agents/              # Agents and AgentFactory
|   |-- api/                 # FastAPI and WebSockets
|   |-- infrastructure/      # Event bus and circuit breaker
|   |-- models/              # Domain entities and request DTOs
|   |-- services/            # Orchestrator and application services
|   |-- storage/             # External clients and repository
|   |-- strategies/          # Strategy contract and implementations
|   |-- tasks/               # Celery tasks and Beat schedules
|   |-- tests/
|   |-- utils/
|   |-- data/                # Default runtime data; ignored by Git
|   |-- requirements.txt
|   `-- requirements-ml.txt
|-- frontend/
|   |-- app/                 # React dashboard
|   |-- public/
|   |-- tests/
|   |-- package.json
|   `-- package-lock.json
|-- infrastructure/docker/   # Dockerfiles and DB initialization
|-- scripts/                 # Start, storage, DB, backup helpers
|-- docs/
|-- .env.example
|-- docker-compose.yml
`-- README.md
```

## Setup and configuration

### Prerequisites

Recommended Windows demo environment:

- Windows 10/11 and PowerShell.
- Docker Desktop with Linux containers and WSL2.
- At least 4 GB available RAM and 10 GB free disk.
- Project stored at `E:\Trading app` or another HDD directory.
- Alpaca paper keys for real market data and paper orders.
- Gemini key for Gemini reasoning; local fallback works without it.

Python and Node are needed only for local development/testing, not normal Docker operation.

### 1. Create the environment file

```powershell
cd "E:\Trading app"
Copy-Item .env.example .env
```

Do not overwrite an existing `.env` that already contains keys. Never commit or paste it into logs/chat.

Generate independent URL-safe secrets:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run that separately for PostgreSQL, Redis, and the optional application key.

### 2. HDD path

The default is:

```dotenv
HDD_STORAGE_PATH=./backend/data
```

Because this project is on `E:`, it resolves to `E:\Trading app\backend\data`. You do not need to provide the path again.

For a separate HDD folder:

```powershell
powershell -File scripts/setup_hdd.ps1 -StoragePath E:\VectorTradingData
```

Then set `HDD_STORAGE_PATH=E:/VectorTradingData`. Docker Desktop must have drive access.

### 3. TimescaleDB

```dotenv
POSTGRES_USER=vector
POSTGRES_PASSWORD=REPLACE_WITH_UNIQUE_URL_SAFE_PASSWORD
POSTGRES_DB=vector
```

Compose builds the internal `DATABASE_URL`. One TimescaleDB service provides PostgreSQL and time-series storage.

### 4. Redis

Redis uses the built-in `default` username. No separate username creation is needed.

```dotenv
REDIS_PASSWORD=REPLACE_WITH_DIFFERENT_URL_SAFE_PASSWORD
REDIS_URL=redis://default:REPLACE_WITH_REDIS_PASSWORD@localhost:6379/0
```

Compose changes the hostname to `redis` inside containers. Redis is capped at 500 MB, uses LRU eviction, and persists RDB snapshots to the HDD.

Verify after startup:

```powershell
docker compose --env-file .env -f docker-compose.yml exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
```

Expected: `PONG`.

### 5. Alpaca paper trading

1. Sign in to Alpaca.
2. Select **Paper Trading**.
3. Generate paper API credentials.
4. Set:

```dotenv
ALPACA_API_KEY=REPLACE_WITH_PAPER_KEY
ALPACA_SECRET_KEY=REPLACE_WITH_PAPER_SECRET
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
```

The application rejects live broker URLs. Market history uses the IEX feed.

### 6. Gemini Flash

Create a key in Google AI Studio:

```dotenv
GEMINI_API_KEY=REPLACE_WITH_GEMINI_KEY
GEMINI_MODEL=gemini-3.6-flash
```

Missing keys, quota failures, and timeouts use a labeled local fallback.

### 7. Application API key

For localhost-only evaluation, `API_KEY` may remain blank. Before network exposure:

```dotenv
API_KEY=REPLACE_WITH_LONG_RANDOM_VALUE
```

REST clients must send `X-API-Key`. Enter the same value in the dashboard's **Local API Access** field. This key is separate from Alpaca and Gemini credentials.

## One-command startup

From `E:\Trading app`:

```powershell
docker compose --env-file .env -f docker-compose.yml up -d --build
```

This starts all six services:

- `timescaledb`: relational/time-series database.
- `redis`: events, Celery broker/results, and locks.
- `api`: FastAPI, orchestrator, agents, REST, and WebSockets.
- `frontend`: React dashboard.
- `worker`: executes scheduled tasks.
- `scheduler`: creates periodic tasks.

Verify:

```powershell
docker compose --env-file .env -f docker-compose.yml ps -a
```

Every service should show `Up`; API, Redis, and TimescaleDB should show `healthy`.

Open:

- Dashboard: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>
- Deep health: <http://localhost:8000/health/deep>

Press `Ctrl+F5` if the dashboard was open during a rebuild.

Lifecycle commands:

```powershell
# Show services
docker compose --env-file .env -f docker-compose.yml ps -a

# Watch logs; Ctrl+C stops watching, not the containers
docker compose --env-file .env -f docker-compose.yml logs -f api worker scheduler

# Apply code/config changes
docker compose --env-file .env -f docker-compose.yml up -d --build

# Stop containers
docker compose --env-file .env -f docker-compose.yml down
```

Do not add `-v` merely to stop the stack. Treat database files as valuable.

## Dashboard and automation

Dashboard data paths:

- Portfolio, performance, agent/system status, and counts refresh over REST.
- Historical bars load immediately over REST.
- New prices use `/ws/market`.
- Verified quote polling is the fallback when WebSocket ticks are delayed.
- The source badge displays `ALPACA` or `SYNTHETIC`.

Controls:

- **Run analysis:** one safe analysis-only cycle.
- **Auto trade:** permission for future scheduled paper orders.
- **Emergency stop:** disables Auto trade, blocks cycles, and cancels pending paper orders.
- **Symbol selector:** AAPL, MSFT, or SPY.

Default schedule:

```text
Every 60 seconds:  Alpaca order reconciliation
Every 300 seconds: 15-minute AAPL, MSFT, and SPY cycles
Every 60 seconds:  dashboard market-stream refresh
```

Celery concurrency is two, so the third symbol may finish after the first two when Gemini is slow.

## API reference

Use <http://localhost:8000/docs> for interactive schemas.

Health/status:

- `GET /health`
- `GET /health/deep`
- `GET /api/v1/agents/status`
- `GET /api/v1/orchestrator/status`
- `GET /api/v1/data/stats`

Market/account:

- `GET /api/v1/market/quotes?symbol=AAPL`
- `GET /api/v1/market/history?symbol=AAPL&days=30`
- `GET /api/v1/portfolio`
- `GET /api/v1/performance`

Analysis:

- `POST /api/v1/orchestrator/run`
- `POST /api/v1/orchestrator/scheduled-run` (internal scheduler)
- `POST /api/v1/agents/strategy/select`
- `GET /api/v1/backtest?strategy=momentum&symbol=AAPL&days=90`

Orders/controls:

- `POST /api/v1/trade/order` requires `confirm_paper=true`
- `GET /api/v1/trade/orders`
- `DELETE /api/v1/trade/order/{order_id}`
- `POST /api/v1/orchestrator/auto-trade`
- `POST /api/v1/orchestrator/emergency-stop`
- `POST /api/v1/orchestrator/resume`
- `POST /api/v1/orchestrator/reconcile`
- `POST /api/v1/orchestrator/feedback`

WebSockets: `/ws/market`, `/ws/orders`, `/ws/agents`, `/ws/alerts`, and `/ws/performance`.

Analysis-only example:

```powershell
$body = @{ symbol = "AAPL"; timeframe = 15; execute = $false } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/orchestrator/run -ContentType application/json -Body $body
```

Enable unattended paper-order permission:

```powershell
$body = @{ enabled = $true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/orchestrator/auto-trade -ContentType application/json -Body $body
```

Run the second command only when unattended paper orders are intentional. If `API_KEY` is configured, add `-Headers @{ "X-API-Key" = "YOUR_APPLICATION_API_KEY" }`.

## HDD storage and backup

Default persistent paths:

```text
backend/data/
|-- postgres/                 # TimescaleDB files
|-- redis/                    # Redis data
`-- app/
    |-- logs/
    |-- state/system.json     # cycles and safety state
    |-- knowledge/scenarios.jsonl
    |-- knowledge/chroma/     # optional
    |-- models/rl_policy.npz
    `-- celerybeat-schedule
```

Database records:

- `market_data`: deduplicated OHLCV bars.
- `indicator_values`: indicator snapshots.
- `agent_events`: compact events.
- `orders`: local paper-order state.

The dashboard's bar count is stored rows, not decisions or trades.

Backup the default database:

```powershell
powershell -File scripts/backup.ps1 -Destination .\backend\data\backups
```

Test restoration against a disposable database before relying on a backup.

## Local development

Backend:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m uvicorn backend.api.main:app --reload --port 8000
```

Frontend in a second terminal:

```powershell
cd frontend
npm.cmd ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm.cmd run dev
```

Without Redis/Celery, manual analysis still works. Without Alpaca keys, the system uses synthetic data and a simulated broker; automatic trading cannot be enabled against that broker.

Optional ML/vector packages:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-ml.txt
```

## Testing and monitoring

Backend:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend:

```powershell
cd frontend
npm.cmd run lint
npm.cmd test
```

Compose validation:

```powershell
docker compose --env-file .env -f docker-compose.yml config
```

Runtime monitoring:

```powershell
docker compose --env-file .env -f docker-compose.yml ps -a
docker compose --env-file .env -f docker-compose.yml logs -f api worker scheduler redis timescaledb
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/deep
Invoke-RestMethod http://localhost:8000/api/v1/orchestrator/status
Invoke-RestMethod http://localhost:8000/api/v1/data/stats
Invoke-RestMethod http://localhost:8000/api/v1/trade/orders
```

When `API_KEY` is configured, pass `-Headers @{ "X-API-Key" = "YOUR_APPLICATION_API_KEY" }` to protected requests. The basic `/health` endpoint remains public.

### 24-hour acceptance test

Any meaningful code/configuration change starts a fresh soak period. For 24 hours verify:

- No unexpected exits or restarts.
- Database and Redis stay healthy.
- Scheduled cycles/reconciliation keep completing.
- Agent failures do not steadily increase.
- Bars, indicators, and events increase.
- Executable decisions use Alpaca data.
- Orders and positions match Alpaca's paper dashboard.
- Memory stays below 85% and free disk above 2 GB.
- Auto trade state matches your intention after restarts.

## Troubleshooting

### Dashboard empty or UNKNOWN

1. Open <http://localhost:8000/health>.
2. Press `Ctrl+F5`.
3. Test the history endpoint in Swagger.
4. Inspect API logs for Alpaca failures.
5. Check whether the badge says `ALPACA` or `SYNTHETIC`.

The chart loads REST history, then WebSocket ticks, then REST quote polling fallback.

### Worker/scheduler not running

```powershell
docker compose --env-file .env -f docker-compose.yml up -d --build worker scheduler
docker compose --env-file .env -f docker-compose.yml ps -a
docker compose --env-file .env -f docker-compose.yml logs --tail 200 worker scheduler
```

`CONNECTED` in the UI refers to the browser WebSocket; it does not prove Celery is running.

### Auto trade ON but no order

This may be correct. Common reasons: HOLD, confidence below 55%, closed market, stale bars, synthetic data, insufficient buying power, daily-loss limit, position cap, or an existing symbol order.

### `npm ci` lock-file mismatch

```powershell
cd frontend
npm.cmd install
npm.cmd test
```

Commit `package.json` and `package-lock.json` together.

### Very large Docker context

Confirm root `.dockerignore` excludes `node_modules`, `.venv`, runtime data, logs, caches, and build output.

### API returns 401

Send `X-API-Key` and enter the same application key in the dashboard. It is not the Alpaca or Gemini key.

### Redis authentication fails

Confirm `REDIS_PASSWORD` matches the password in `REDIS_URL`; the username is `default`. Then:

```powershell
docker compose --env-file .env -f docker-compose.yml up -d --force-recreate redis api worker scheduler
```

### Gemini local fallback

Check `/health/deep`, key, quota, network, and model name. A fallback is non-fatal and labeled in cycle output.

## Known limitations

- Alpaca paper trading only; live-money URLs are rejected.
- Default feed is IEX, not a consolidated exchange-grade feed.
- Fixed schedules are not exchange calendars; execution gates check market status and freshness.
- Knowledge and RL are demo-scale and require completed, reconciled outcomes.
- The dashboard is a local console, not a hardened multi-user terminal.
- `API_KEY` is shared-key protection, not HTTPS, RBAC, or a secrets manager.
- Emergency stop does not liquidate filled positions.
- No strategy or model guarantees profit.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for additional implementation notes.
