from backend.models.domain.entities import MarketSnapshot,Side
from backend.strategies.base import TradingStrategy
class TrendFollowingStrategy(TradingStrategy):
    name="trend_following"
    def generate(self,s:MarketSnapshot):
        fast=s.indicators.get("ema_12",0);slow=s.indicators.get("ema_26",0);price=s.bars[-1].close
        gap=(fast-slow)/max(price,1);action=Side.BUY if gap>.0005 else Side.SELL if gap<-.0005 else Side.HOLD
        return self.signal(s,action,min(.9,.55+abs(gap)*50),"Fast and slow exponential trend alignment")
