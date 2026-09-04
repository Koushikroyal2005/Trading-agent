"""Dependency-light technical indicators for 1–60 minute bars."""
from __future__ import annotations

import numpy as np


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.empty_like(values, dtype=float); alpha = 2 / (period + 1); result[0] = values[0]
    for index in range(1, len(values)): result[index] = alpha * values[index] + (1 - alpha) * result[index - 1]
    return result


def calculate_indicators(closes: list[float], highs: list[float], lows: list[float], volumes: list[float]) -> dict[str, float]:
    c=np.asarray(closes,dtype=float); h=np.asarray(highs,dtype=float); l=np.asarray(lows,dtype=float); v=np.asarray(volumes,dtype=float)
    if len(c)<2: return {"close":float(c[-1]) if len(c) else 0.0}
    returns=np.diff(c)/np.maximum(c[:-1],1e-9); ema12=_ema(c,12); ema26=_ema(c,26); macd=ema12-ema26; signal=_ema(macd,9)
    window=c[-min(20,len(c)):]; mean=float(window.mean()); std=float(window.std()); delta=np.diff(c); gains=np.clip(delta,0,None); losses=-np.clip(delta,None,0); avg_gain=float(gains[-14:].mean()) if gains.size else 0; avg_loss=float(losses[-14:].mean()) if losses.size else 0; rsi=100 if avg_loss==0 else 100-(100/(1+avg_gain/avg_loss))
    prev=np.r_[c[0],c[:-1]]; true_range=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev))); atr=float(true_range[-14:].mean()); typical=(h+l+c)/3; vwap=float(np.sum(typical*v)/max(np.sum(v),1)); high20=float(h[-20:].max()); low20=float(l[-20:].min()); momentum=float(c[-1]-c[max(0,len(c)-11)]); volatility=float(returns[-20:].std()*np.sqrt(252)) if returns.size else 0
    return {"close":float(c[-1]),"sma_5":float(c[-5:].mean()),"sma_10":float(c[-10:].mean()),"sma_20":mean,"ema_12":float(ema12[-1]),"ema_26":float(ema26[-1]),"macd":float(macd[-1]),"macd_signal":float(signal[-1]),"macd_histogram":float(macd[-1]-signal[-1]),"rsi":rsi,"bollinger_upper":mean+2*std,"bollinger_middle":mean,"bollinger_lower":mean-2*std,"atr":atr,"vwap":vwap,"momentum_10":momentum,"roc_10":float(momentum/max(c[max(0,len(c)-11)],1e-9)*100),"volatility":volatility,"support":low20,"resistance":high20,"volume_sma_20":float(v[-20:].mean()),"volume_ratio":float(v[-1]/max(v[-20:].mean(),1)),"high_low_range":float((h[-1]-l[-1])/max(c[-1],1e-9)),"return_1":float(returns[-1]),"obv_proxy":float(np.sum(np.sign(np.diff(c))*v[1:])),"stochastic_k":float((c[-1]-low20)/max(high20-low20,1e-9)*100)}

