from backend.models.domain.entities import MarketSnapshot,Side
from backend.strategies.base import TradingStrategy
class BreakoutStrategy(TradingStrategy):
    name="breakout"
    def generate(self,s:MarketSnapshot):
        price=s.bars[-1].close;res=s.indicators.get("resistance",price);support=s.indicators.get("support",price);volume=s.indicators.get("volume_ratio",1)
        action=Side.BUY if price>=res and volume>1.1 else Side.SELL if price<=support and volume>1.1 else Side.HOLD
        return self.signal(s,action,min(.9,.55+max(0,volume-1)*.2),"Twenty-bar breakout with volume confirmation")
