from backend.models.domain.entities import MarketSnapshot,Side
from backend.strategies.base import TradingStrategy
class MeanReversionStrategy(TradingStrategy):
    name="mean_reversion"
    def generate(self,s:MarketSnapshot):
        price=s.bars[-1].close;lower=s.indicators.get("bollinger_lower",price);upper=s.indicators.get("bollinger_upper",price);rsi=s.indicators.get("rsi",50)
        action=Side.BUY if price<=lower and rsi<40 else Side.SELL if price>=upper and rsi>60 else Side.HOLD
        return self.signal(s,action,.72 if action!=Side.HOLD else .45,"Bollinger deviation with RSI confirmation")
