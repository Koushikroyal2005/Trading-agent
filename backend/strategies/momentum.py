from backend.models.domain.entities import MarketSnapshot,Side
from backend.strategies.base import TradingStrategy

class MomentumStrategy(TradingStrategy):
    name="momentum"
    def generate(self,s:MarketSnapshot):
        rsi=s.indicators.get("rsi",50);momentum=s.indicators.get("momentum_10",0);macd=s.indicators.get("macd_histogram",0)
        action=Side.BUY if momentum>0 and macd>=0 and rsi<75 else Side.SELL if momentum<0 and macd<0 and rsi>25 else Side.HOLD
        confidence=min(.95,.5+abs(momentum)/max(s.bars[-1].close,1)*10+abs(macd)/max(s.bars[-1].close,1))
        return self.signal(s,action,confidence,"Price momentum and MACD alignment")
