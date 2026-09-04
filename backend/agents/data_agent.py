from __future__ import annotations
import math,random
from datetime import timedelta
from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketBar,MarketDataSource,MarketRegime,MarketSnapshot,utc_now
from backend.utils.indicators import calculate_indicators

class DataAgent(BaseAgent[dict,MarketSnapshot]):
    def __init__(self,*args,market_client=None,allow_synthetic_data:bool=True,**kwargs):
        super().__init__("data",*args,**kwargs)
        self.market_client=market_client
        self.allow_synthetic_data=allow_synthetic_data
    async def _process(self,input_data:dict)->MarketSnapshot:
        symbol=input_data.get("symbol","AAPL").upper();timeframe=int(input_data.get("timeframe",15));limit=min(int(input_data.get("limit",100)),10_000)
        bars=await self.market_client.history(symbol,timeframe,limit) if self.market_client else []
        source=MarketDataSource.ALPACA
        if not bars:
            if not self.allow_synthetic_data:
                raise RuntimeError(f"No verified Alpaca bars available for {symbol}")
            bars=self._synthetic(symbol,timeframe)
            source=MarketDataSource.SYNTHETIC
        indicators=calculate_indicators([b.close for b in bars],[b.high for b in bars],[b.low for b in bars],[b.volume for b in bars]);regime=self._regime(indicators)
        return MarketSnapshot(symbol=symbol,timeframe_minutes=timeframe,bars=bars,indicators=indicators,regime=regime,source=source)
    @staticmethod
    def _regime(i:dict[str,float])->MarketRegime:
        if i.get("volatility",0)>.45:return MarketRegime.VOLATILE
        if i.get("ema_12",0)>i.get("ema_26",0)*1.001:return MarketRegime.BULLISH
        if i.get("ema_12",0)<i.get("ema_26",0)*.999:return MarketRegime.BEARISH
        return MarketRegime.RANGING
    @staticmethod
    def _synthetic(symbol:str,timeframe:int)->list[MarketBar]:
        rng=random.Random(sum(map(ord,symbol))+timeframe);price=100+sum(map(ord,symbol))%150;now=utc_now();bars=[]
        for index in range(100):
            drift=.0005+math.sin(index/12)*.0004;change=price*(drift+rng.gauss(0,.002));open_price=price;price=max(1,price+change);spread=abs(rng.gauss(price*.0015,price*.0004));volume=max(1000,rng.gauss(250_000,50_000));bars.append(MarketBar(symbol=symbol,timestamp=now-timedelta(minutes=(99-index)*timeframe),open=open_price,high=max(open_price,price)+spread,low=min(open_price,price)-spread,close=price,volume=volume,vwap=(open_price+price)/2,trade_count=int(volume/100)))
        return bars
