from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import Portfolio,RiskDecision,Side,TradeSignal
from backend.utils.risk_metrics import kelly_fraction,sharpe_ratio,value_at_risk

class RiskAgent(BaseAgent[dict,RiskDecision]):
    def __init__(self,*args,max_position_pct:float=.05,max_daily_loss_pct:float=.02,**kwargs):super().__init__("risk",*args,**kwargs);self.max_position_pct=max_position_pct;self.max_daily_loss_pct=max_daily_loss_pct
    async def _process(self,input_data:dict)->RiskDecision:
        signal:TradeSignal=input_data["signal"];portfolio:Portfolio=input_data["portfolio"];returns=input_data.get("returns",[])
        if signal.action==Side.HOLD:return RiskDecision(approved=False,reason="hold signal")
        if portfolio.equity<=0 or portfolio.buying_power<=0:return RiskDecision(approved=False,reason="insufficient broker equity or buying power")
        if portfolio.daily_pnl<=-portfolio.equity*self.max_daily_loss_pct:return RiskDecision(approved=False,reason="daily loss limit reached")
        position=next((item for item in portfolio.positions if item.symbol==signal.symbol),None)
        same_direction=bool(position and ((position.quantity>0 and signal.action==Side.BUY) or (position.quantity<0 and signal.action==Side.SELL)))
        remaining_exposure=max(0,portfolio.equity*self.max_position_pct-(abs(position.market_value) if same_direction and position else 0))
        exposure_quantity=(abs(position.quantity) if position and not same_direction else remaining_exposure/signal.entry_price)
        stop_distance=abs(signal.entry_price-signal.stop_loss);risk_budget=portfolio.equity*min(.01,self.max_daily_loss_pct);kelly=min(.5,kelly_fraction(.55,2));quantity=min(exposure_quantity,portfolio.buying_power/signal.entry_price,risk_budget/max(stop_distance,1e-9))*max(.25,kelly)
        approved=quantity>0 and signal.confidence>=.55
        return RiskDecision(approved=approved,reason="risk checks passed" if approved else "confidence below threshold",quantity=round(quantity,4) if approved else 0,risk_percentage=(quantity*stop_distance/portfolio.equity if approved else 0),var_95=value_at_risk(returns),sharpe_ratio=sharpe_ratio(returns))
