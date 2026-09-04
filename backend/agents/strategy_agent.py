from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketSnapshot,TradeSignal
from backend.strategies.base import StrategyRegistry

class StrategyAgent(BaseAgent[dict,TradeSignal]):
    def __init__(self,*args,registry:StrategyRegistry,**kwargs):super().__init__("strategy",*args,**kwargs);self.registry=registry;self.selected="auto"
    def select(self,name:str)->None:self.registry.get(name);self.selected=name.lower().replace(" ","_")
    async def _process(self,input_data:dict)->TradeSignal:
        snapshot:MarketSnapshot=input_data["snapshot"];recommended=input_data.get("recommended_strategy")
        fallback={"bullish":"momentum","bearish":"trend_following","ranging":"mean_reversion","volatile":"breakout"}[snapshot.regime.value]
        if self.selected!="auto":name=self.selected
        else:
            normalized=str(recommended or "").strip().lower().replace("-","_").replace(" ","_")
            name=next((candidate for candidate in self.registry.names() if candidate in normalized),fallback)
        return self.registry.get(name).generate(snapshot)
