"""Factory pattern wiring dependencies without coupling agents to frameworks."""
from backend.agents.cot_agent import CoTAgent
from backend.agents.data_agent import DataAgent
from backend.agents.execution_agent import ExecutionAgent
from backend.agents.knowledge_agent import KnowledgeAgent
from backend.agents.risk_agent import RiskAgent
from backend.agents.rl_agent import RLAgent
from backend.agents.strategy_agent import StrategyAgent
from backend.agents.validation_agent import ValidationAgent

class AgentFactory:
    def __init__(self,event_bus,settings,repository,broker,reasoning_client,registry):self.bus=event_bus;self.settings=settings;self.repository=repository;self.broker=broker;self.reasoning=reasoning_client;self.registry=registry
    def create_all(self)->dict:
        common={"event_bus":self.bus,"timeout_seconds":self.settings.agent_timeout_seconds}
        market_client=self.broker if hasattr(self.broker,"history") else None
        data_common={**common,"timeout_seconds":max(15,self.settings.agent_timeout_seconds)}
        cot_common={**common,"timeout_seconds":max(50,self.settings.agent_timeout_seconds)}
        return {"data":DataAgent(**data_common,market_client=market_client,allow_synthetic_data=self.settings.allow_synthetic_data),"knowledge":KnowledgeAgent(**common,storage_path=self.settings.hdd_storage_path),"cot":CoTAgent(**cot_common,reasoning_client=self.reasoning),"strategy":StrategyAgent(**common,registry=self.registry),"risk":RiskAgent(**common,max_position_pct=self.settings.max_position_percentage,max_daily_loss_pct=self.settings.max_daily_loss_percentage),"execution":ExecutionAgent(**common,broker=self.broker,repository=self.repository),"rl":RLAgent(**common,storage_path=self.settings.hdd_storage_path),"validation":ValidationAgent(**common)}
