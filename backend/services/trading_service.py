"""Command pattern for execution and cancellation (undo)."""
from abc import ABC,abstractmethod
from backend.models.domain.entities import AgentEvent,Order

class TradeCommand(ABC):
    @abstractmethod
    async def execute(self):...
    @abstractmethod
    async def undo(self):...

class PlaceOrderCommand(TradeCommand):
    def __init__(self,broker,repository,order:Order):self.broker=broker;self.repository=repository;self.order=order
    async def execute(self)->Order:self.order=await self.broker.submit_order(self.order);await self.repository.save_order(self.order);return self.order
    async def undo(self)->bool:
        if not self.order.broker_id:return False
        result=await self.broker.cancel_order(self.order.broker_id);self.order.status="cancelled" if result else self.order.status;await self.repository.save_order(self.order);return result

class TradingService:
    def __init__(self,broker,repository,event_bus=None):self.broker=broker;self.repository=repository;self.event_bus=event_bus;self.commands:dict[str,PlaceOrderCommand]={}
    async def place(self,order:Order)->Order:
        command=PlaceOrderCommand(self.broker,self.repository,order);result=await command.execute();self.commands[str(result.id)]=command
        if self.event_bus:await self.event_bus.publish(AgentEvent(topic="trade.order.updated",source="trading_service",payload=result.model_dump(mode="json")))
        return result
    async def cancel(self,order_id:str)->bool:
        result=await self.commands[order_id].undo() if order_id in self.commands else await self.broker.cancel_order(order_id)
        if result and self.event_bus:await self.event_bus.publish(AgentEvent(topic="trade.order.cancelled",source="trading_service",payload={"order_id":order_id}))
        return result
