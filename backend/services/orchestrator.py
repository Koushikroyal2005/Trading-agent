"""Safe analysis and opt-in execution orchestration service."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.models.domain.entities import AgentEvent, MarketDataSource
from backend.models.domain.exceptions import OrderRejectedError
from backend.services.system_state import SystemStateCaretaker


class TradingOrchestrator:
    def __init__(self, agents: dict, event_bus, portfolio_service, registry, repository=None, broker=None, state: SystemStateCaretaker | None = None, max_data_age_minutes: int = 20):
        self.agents = agents
        self.bus = event_bus
        self.portfolios = portfolio_service
        self.registry = registry
        self.repository = repository
        self.broker = broker
        self.state = state
        self.max_data_age_minutes = max_data_age_minutes
        self.running = False
        self.auto_trade = False
        self.emergency_stopped = False
        self.cycles = 0
        self.learned_closed_trades = 0
        self.last_snapshot = None
        self.last_signal = None

    async def initialize(self):
        restored = self.state.restore() if self.state else None
        if restored:
            self.cycles = restored.cycles
            self.auto_trade = restored.auto_trade
            self.emergency_stopped = restored.emergency_stopped
            self.learned_closed_trades = restored.learned_closed_trades
            if restored.selected_strategy != "auto": self.agents["strategy"].select(restored.selected_strategy)
        for agent in self.agents.values(): await agent.initialize()
        self.running = not self.emergency_stopped

    def _save_state(self) -> None:
        if self.state:
            self.state.save(self.cycles, self.agents["strategy"].selected, self.auto_trade, self.emergency_stopped, self.learned_closed_trades)

    async def _execution_guard(self, snapshot) -> tuple[bool, str]:
        if not self.auto_trade: return False, "auto trading is disabled"
        if self.emergency_stopped or not self.running: return False, "emergency stop is active"
        if snapshot.source != MarketDataSource.ALPACA: return False, "synthetic data cannot be traded"
        age_minutes = (datetime.now(timezone.utc) - snapshot.bars[-1].timestamp).total_seconds() / 60
        if age_minutes > self.max_data_age_minutes: return False, f"market data is stale ({age_minutes:.1f} minutes)"
        if not self.broker or getattr(self.broker, "is_simulated", True): return False, "verified Alpaca paper broker is required"
        clock = await self.broker.get_clock()
        if not clock.get("is_open", False): return False, "Alpaca reports that the market is closed"
        open_orders = await self.broker.list_orders(status="open", limit=100)
        if any(item.get("symbol") == snapshot.symbol for item in open_orders): return False, "an open broker order already exists for this symbol"
        return True, "execution safety checks passed"

    async def run_cycle(self, symbol: str, timeframe: int = 15, execute: bool = False) -> dict:
        if self.emergency_stopped: raise RuntimeError("emergency stop is active")
        snapshot = await self.agents["data"].process({"symbol": symbol, "timeframe": timeframe})
        if self.repository: await self.repository.save_snapshot(snapshot)
        knowledge = await self.agents["knowledge"].process({"snapshot": snapshot})
        reasoning = await self.agents["cot"].process({"snapshot": snapshot, "knowledge": knowledge})
        signal = await self.agents["strategy"].process({"snapshot": snapshot, "recommended_strategy": reasoning.get("strategy_recommendation")})
        portfolio = await self.portfolios.get()
        closes = [bar.close for bar in snapshot.bars]
        returns = [closes[index] / closes[index-1] - 1 for index in range(1, len(closes))]
        risk = await self.agents["risk"].process({"signal": signal, "portfolio": portfolio, "returns": returns})
        allowed, guard_reason = await self._execution_guard(snapshot) if execute else (False, "analysis-only cycle")
        order = None
        if allowed:
            try:
                order = await self.agents["execution"].process({"signal": signal, "risk": risk, "data_source": snapshot.source})
            except OrderRejectedError as error:
                allowed = False
                guard_reason = str(error)
        policy = await self.agents["rl"].process({"snapshot": snapshot})
        self.cycles += 1
        self.last_snapshot, self.last_signal = snapshot, signal
        self._save_state()
        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "symbol": symbol, "timeframe": timeframe, "data_source": snapshot.source.value, "regime": snapshot.regime.value, "decision": signal.model_dump(mode="json"), "reasoning": reasoning, "knowledge": knowledge, "risk": risk.model_dump(mode="json"), "order": order.model_dump(mode="json") if order else None, "execution": {"requested": execute, "allowed": allowed, "reason": guard_reason}, "rl_policy": policy, "cycle": self.cycles}
        await self.bus.publish(AgentEvent(topic="trading.cycle.completed", source="orchestrator", payload=result))
        return result

    async def record_outcome(self, pnl: float, sharpe: float, win_rate: float, drawdown: float) -> dict:
        if not self.last_snapshot or not self.last_signal: raise RuntimeError("run a trading cycle before recording feedback")
        aif = await self.agents["cot"].client.score_trade({"pnl": pnl, "sharpe": sharpe, "win_rate": win_rate, "drawdown": drawdown, "strategy": self.last_signal.strategy})
        reward = await self.agents["rl"].learn(self.last_snapshot, self.last_signal.action, pnl, sharpe, win_rate, drawdown, aif)
        await self.agents["knowledge"].remember(self.last_snapshot, self.last_signal.strategy, pnl)
        result = {"learned": True, "reward": reward, "aif_score": aif, "replay_size": len(self.agents["rl"].buffer), "updates": self.agents["rl"].updates}
        await self.bus.publish(AgentEvent(topic="trading.learning.completed", source="orchestrator", payload=result))
        return result

    async def reconcile(self) -> dict:
        remote_orders = await self.broker.list_orders() if self.broker else []
        updated = 0
        local_orders = await self.repository.list_orders(limit=5000)
        for item in remote_orders:
            client_id = item.get("client_order_id", "")
            if not client_id.startswith("vector-"): continue
            match = next((order for order in local_orders if order.get("client_order_id") == client_id), None)
            if not match: continue
            match.update({"broker_id": item.get("id"), "status": item.get("status", match["status"]), "filled_price": float(item["filled_avg_price"]) if item.get("filled_avg_price") else match.get("filled_price")})
            from backend.models.domain.entities import Order, Side
            from uuid import NAMESPACE_URL, uuid5
            await self.repository.save_order(Order.model_validate(match)); updated += 1
            for leg in item.get("legs") or []:
                leg_order = Order(id=uuid5(NAMESPACE_URL, str(leg["id"])), broker_id=str(leg["id"]), symbol=leg["symbol"], side=Side(leg["side"]), quantity=float(leg["qty"]), status=leg.get("status","new"), filled_price=float(leg["filled_avg_price"]) if leg.get("filled_avg_price") else None, strategy=match.get("strategy","reconciled_bracket"), client_order_id=leg.get("client_order_id"), data_source=match.get("data_source"))
                await self.repository.save_order(leg_order); updated += 1
        performance = await self.repository.performance()
        if performance["closed_trades"] > self.learned_closed_trades and self.last_snapshot:
            await self.record_outcome(float(performance["total_return"]), float(performance["sharpe_ratio"]), float(performance["win_rate"]), float(performance["max_drawdown"]))
            self.learned_closed_trades = int(performance["closed_trades"]); self._save_state()
        result = {"broker_orders": len(remote_orders), "updated": updated, "closed_trades": performance["closed_trades"], "learned_closed_trades": self.learned_closed_trades}
        await self.bus.publish(AgentEvent(topic="trading.reconciliation.completed", source="orchestrator", payload=result))
        return result

    def set_auto_trade(self, enabled: bool) -> None:
        if enabled and self.emergency_stopped: raise RuntimeError("resume before enabling auto trading")
        if enabled and (not self.broker or getattr(self.broker,"is_simulated",True)): raise RuntimeError("verified Alpaca paper credentials are required")
        self.auto_trade = enabled; self._save_state()

    async def emergency_stop(self) -> int:
        self.auto_trade = False; self.emergency_stopped = True; self.running = False; self._save_state()
        return await self.broker.cancel_all_orders() if self.broker and hasattr(self.broker, "cancel_all_orders") else 0

    def resume(self) -> None:
        self.emergency_stopped = False; self.running = True; self.auto_trade = False; self._save_state()

    async def backtest(self, strategy_name: str, symbol: str = "AAPL", days: int = 90) -> dict:
        snapshot = await self.agents["data"].process({"symbol": symbol, "timeframe": 60, "limit": min(days*7, 10_000)})
        strategy = self.registry.get(strategy_name)
        return await self.agents["validation"].process({"snapshot": snapshot, "strategy": strategy, "days": days})

    def statuses(self): return [agent.get_status().model_dump(mode="json") for agent in self.agents.values()]

    def system_status(self) -> dict:
        return {"running": self.running, "auto_trade": self.auto_trade, "emergency_stopped": self.emergency_stopped, "cycles": self.cycles, "learned_closed_trades": self.learned_closed_trades}
