from backend.models.domain.entities import MarketSnapshot,Side
from backend.strategies.base import TradingStrategy
class SwingStrategy(TradingStrategy):
    name="swing"
    def generate(self,s:MarketSnapshot):
        rsi=s.indicators.get("rsi",50);price=s.bars[-1].close;vwap=s.indicators.get("vwap",price)
        action=Side.BUY if 40<=rsi<=60 and price>vwap else Side.SELL if 40<=rsi<=60 and price<vwap else Side.HOLD
        return self.signal(s,action,.64 if action!=Side.HOLD else .4,"VWAP swing setup with neutral RSI")

