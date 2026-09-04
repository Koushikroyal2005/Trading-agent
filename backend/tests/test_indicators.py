from backend.utils.indicators import calculate_indicators
from backend.utils.risk_metrics import kelly_fraction,max_drawdown,sharpe_ratio,value_at_risk

def test_calculates_twenty_indicators():
    closes=[100+i*.2 for i in range(40)];result=calculate_indicators(closes,[v+1 for v in closes],[v-1 for v in closes],[1000+i*10 for i in range(40)])
    assert len(result)>=20
    assert result["rsi"]>50
    assert result["bollinger_upper"]>result["bollinger_lower"]

def test_risk_metrics_are_bounded():
    assert 0<=kelly_fraction(.55,2)<=1
    assert value_at_risk([-.03,-.01,.01,.02])>=0
    assert sharpe_ratio([-.01,.01,.02])!=0
    assert max_drawdown([100,110,99,120])==.1

