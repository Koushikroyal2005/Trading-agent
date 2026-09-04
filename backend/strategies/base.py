"""Strategy pattern contracts and registry."""
from abc import ABC,abstractmethod

from backend.models.domain.entities import MarketSnapshot,Side,TradeSignal


class TradingStrategy(ABC):
    name="base"
    @abstractmethod
    def generate(self,snapshot:MarketSnapshot)->TradeSignal: ...
    def position_sizing(self,confidence:float)->float:return max(0.1,min(1.0,confidence))
    def risk_parameters(self,price:float,atr:float,side:Side)->tuple[float,float]:
        distance=max(atr*1.5,price*.005)
        return (price-distance,price+distance*2) if side==Side.BUY else (price+distance,price-distance*2)
    def signal(self,snapshot:MarketSnapshot,action:Side,confidence:float,rationale:str)->TradeSignal:
        price=snapshot.bars[-1].close;stop,target=self.risk_parameters(price,snapshot.indicators.get("atr",price*.01),action)
        return TradeSignal(symbol=snapshot.symbol,action=action,confidence=max(0,min(1,confidence)),strategy=self.name,entry_price=price,stop_loss=stop,take_profit=target,rationale=rationale)


class StrategyRegistry:
    def __init__(self):self._strategies:dict[str,TradingStrategy]={}
    def register(self,strategy:TradingStrategy)->None:self._strategies[strategy.name.lower()]=strategy
    def get(self,name:str)->TradingStrategy:
        key=name.lower().replace(" ","_")
        if key not in self._strategies:raise KeyError(f"unknown strategy: {name}")
        return self._strategies[key]
    def names(self)->list[str]:return sorted(self._strategies)

