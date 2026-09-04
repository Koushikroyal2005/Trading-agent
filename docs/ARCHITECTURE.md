# Vector architecture

```text
React dashboard ─ REST / WebSocket ─ FastAPI interface adapters
                                      │
                              TradingOrchestrator
                                      │
 DataAgent → KnowledgeAgent → CoTAgent → StrategyAgent → RiskAgent → ExecutionAgent
                                      │                         │
                               ValidationAgent              RLAgent
                                      │
 Redis Stream EventBus (Observer/Pub-Sub) ─ Repository ports ─ Broker / Gemini / DB adapters
```

The domain layer contains validated trading vocabulary and explicit market-data provenance. Application services own analysis, execution gating, reconciliation, and durable safety state. Agents implement a common bounded Template Method interface. External APIs and databases remain replaceable adapters.

Celery Beat schedules analysis through the API-owned orchestrator rather than importing FastAPI globals into a worker. Redis locks prevent overlapping symbol/timeframe cycles. The API writes compact agent messages to a capped Redis Stream and TimescaleDB, while WebSocket subscribers receive the same local events.

Patterns are deliberately concrete: `EventBus` is Observer/Pub-Sub; strategies use Strategy plus a registry; `TradingOrchestrator` is the responsibility chain; `AgentFactory` is Factory; cached settings/logging are process singletons; `PlaceOrderCommand` supports undo; `SystemMemento` restores operating state; agent validation wraps every result as a decorator-like boundary; and `TradingRepository` isolates persistence.

Private model chain-of-thought is neither requested nor stored. The CoT component keeps a concise evidence/decision summary and a fixed audit checklist, which is safer and more stable for production review.
