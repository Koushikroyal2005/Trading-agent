import math
import numpy as np


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    return float(max(0.0, -np.percentile(np.asarray(returns,dtype=float), (1-confidence)*100))) if returns else 0.0


def sharpe_ratio(returns: list[float], periods: int = 252) -> float:
    values=np.asarray(returns,dtype=float)
    return float(values.mean()/values.std()*math.sqrt(periods)) if values.size>1 and values.std()>0 else 0.0


def max_drawdown(equity: list[float]) -> float:
    values=np.asarray(equity,dtype=float)
    if not values.size: return 0.0
    peaks=np.maximum.accumulate(values)
    return float(np.max((peaks-values)/np.maximum(peaks,1e-9)))


def kelly_fraction(win_rate: float, reward_risk: float) -> float:
    if reward_risk<=0: return 0.0
    return float(max(0.0,min(1.0,win_rate-(1-win_rate)/reward_risk)))

