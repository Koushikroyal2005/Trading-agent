"""Template Method base agent with bounded execution and event publication."""
from __future__ import annotations

import asyncio,time
from abc import ABC,abstractmethod
from typing import Any,Generic,TypeVar

from backend.infrastructure.event_bus import EventBus
from backend.models.domain.entities import AgentEvent,AgentState,AgentStatus,MarketSnapshot,utc_now

I=TypeVar("I");O=TypeVar("O")

class BaseAgent(ABC,Generic[I,O]):
    def __init__(self,name:str,event_bus:EventBus,timeout_seconds:float=5):self.name=name;self.event_bus=event_bus;self.timeout_seconds=timeout_seconds;self.status=AgentStatus(name=name,state=AgentState.CREATED)
    async def initialize(self)->None:self.status.state=AgentState.IDLE;self.status.updated_at=utc_now();await self._publish("agent.status",self.status.model_dump(mode="json"))
    async def process(self,input_data:I)->O:
        started=time.perf_counter();self.status.state=AgentState.PROCESSING
        try:
            output=await asyncio.wait_for(self._process(input_data),timeout=self.timeout_seconds)
            if not await self.validate(output):raise ValueError(f"{self.name} produced invalid output")
            self.status.processed+=1;self.status.state=AgentState.IDLE;await self._publish(f"agent.{self.name}.completed",{"output":self._serialize(output)})
            return output
        except Exception as error:
            detail=f"{type(error).__name__}: {error}";self.status.failures+=1;self.status.state=AgentState.ERROR;self.status.last_error=detail;await self.on_error(error);raise
        finally:self.status.last_execution_ms=(time.perf_counter()-started)*1000;self.status.updated_at=utc_now()
    @abstractmethod
    async def _process(self,input_data:I)->O:...
    async def validate(self,output_data:O)->bool:return output_data is not None
    def get_status(self)->AgentStatus:return self.status.model_copy(deep=True)
    async def on_error(self,error:Exception)->str:await self._publish("agent.error",{"error":f"{type(error).__name__}: {error}"});return "retry_or_fallback"
    async def _publish(self,topic:str,payload:dict[str,Any])->None:await self.event_bus.publish(AgentEvent(topic=topic,source=self.name,payload=payload))
    @staticmethod
    def _serialize(value:Any)->Any:
        if isinstance(value,MarketSnapshot):
            latest=value.bars[-1] if value.bars else None
            return {"symbol":value.symbol,"timeframe_minutes":value.timeframe_minutes,"bar_count":len(value.bars),"latest_bar":latest.model_dump(mode="json") if latest else None,"indicators":value.indicators,"regime":value.regime.value,"source":value.source.value}
        return value.model_dump(mode="json") if hasattr(value,"model_dump") else value
