from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketSnapshot

class CoTAgent(BaseAgent[dict,dict]):
    """Produces an auditable decision summary; hidden model reasoning is never persisted."""
    def __init__(self,*args,reasoning_client,**kwargs):super().__init__("cot",*args,**kwargs);self.client=reasoning_client
    async def _process(self,input_data:dict)->dict:
        snapshot:MarketSnapshot=input_data["snapshot"];context=input_data.get("knowledge",[])
        payload={"symbol":snapshot.symbol,"timeframe":snapshot.timeframe_minutes,"regime":snapshot.regime.value,"price":snapshot.bars[-1].close,"indicators":snapshot.indicators,"similar_scenarios":context[:5]}
        result=await self.client.analyze(payload);result["reasoning_chain"]=["Evaluate regime and volatility","Compare retrieved scenarios","Select risk-compatible strategy"]
        return result

