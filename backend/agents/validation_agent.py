from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketSnapshot
from backend.strategies.base import TradingStrategy
from backend.utils.risk_metrics import max_drawdown,sharpe_ratio

class ValidationAgent(BaseAgent[dict,dict]):
    def __init__(self,*args,**kwargs):super().__init__("validation",*args,**kwargs)
    async def _process(self,input_data:dict)->dict:
        snapshot:MarketSnapshot=input_data["snapshot"];strategy:TradingStrategy=input_data["strategy"];bars=snapshot.bars;returns=[];wins=0
        if len(bars)<32:raise ValueError("at least 32 bars are required for validation")
        for index in range(30,len(bars)-1):
            partial=snapshot.model_copy(update={"bars":bars[:index+1]});signal=strategy.generate(partial);ret=(bars[index+1].close/bars[index].close-1)*(1 if signal.action.value=="buy" else -1 if signal.action.value=="sell" else 0);returns.append(ret);wins+=ret>0
        equity=[1]
        for value in returns:equity.append(equity[-1]*(1+value))
        positive=sum(v for v in returns if v>0);negative=abs(sum(v for v in returns if v<0));return {"strategy":strategy.name,"trades":sum(v!=0 for v in returns),"win_rate":wins/max(sum(v!=0 for v in returns),1),"profit_factor":positive/max(negative,1e-9),"sharpe_ratio":sharpe_ratio(returns,252*6.5),"max_drawdown":max_drawdown(equity),"walk_forward":True,"requested_days":input_data.get("days"),"bars_evaluated":len(bars),"data_source":snapshot.source.value}
