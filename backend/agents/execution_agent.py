from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import Order,RiskDecision,TradeSignal

class ExecutionAgent(BaseAgent[dict,Order|None]):
    def __init__(self,*args,broker,repository,**kwargs):super().__init__("execution",*args,**kwargs);self.broker=broker;self.repository=repository
    async def _process(self,input_data:dict)->Order|None:
        signal:TradeSignal=input_data["signal"];risk:RiskDecision=input_data["risk"]
        if not risk.approved:return None
        order=Order(symbol=signal.symbol,side=signal.action,quantity=risk.quantity,strategy=signal.strategy,stop_loss=signal.stop_loss,take_profit=signal.take_profit,data_source=input_data.get("data_source"))
        order=await self.broker.submit_order(order);await self.repository.save_order(order);return order
    async def validate(self,output_data:Order|None)->bool:return output_data is None or output_data.status not in {"rejected","failed"}
