"""Gemini Flash adapter returning concise, auditable conclusions (not private CoT)."""
from __future__ import annotations
import asyncio,json
from backend.infrastructure.circuit_breaker import CircuitBreaker

class GeminiReasoningClient:
    def __init__(self,api_key:str|None,model:str="gemini-2.5-flash"):self.api_key=api_key;self.model=model;self.breaker=CircuitBreaker()
    async def analyze(self,payload:dict)->dict:
        if not self.api_key:return self._fallback(payload)
        async def operation():
            from google import genai
            client=genai.Client(api_key=self.api_key)
            prompt="Return JSON only with keys market_regime, strategy_recommendation, confidence, reasoning_summary. strategy_recommendation must be exactly one of: momentum, mean_reversion, breakout, trend_following, swing. Do not reveal hidden chain-of-thought. Analyze: "+json.dumps(payload,default=str)[:12000]
            response=await asyncio.wait_for(asyncio.to_thread(client.models.generate_content,model=self.model,contents=prompt,config={"response_mime_type":"application/json"}),timeout=40)
            result=json.loads(response.text);result["provider"]=self.model;return result
        try:return await self.breaker.call(operation)
        except Exception as error:
            result=self._fallback(payload);result["fallback_reason"]=f"{type(error).__name__}: {error}"[:300];return result
    async def score_trade(self,payload:dict)->float:
        result=await self.analyze({"task":"score_trade_0_to_1",**payload});return float(max(0,min(1,result.get("confidence",.5))))
    async def health(self)->bool:
        if not self.api_key:return False
        try:
            from google import genai
            client=genai.Client(api_key=self.api_key)
            await asyncio.to_thread(client.models.get,model=self.model)
            return True
        except Exception:return False
    @staticmethod
    def _fallback(payload:dict)->dict:
        regime=payload.get("regime","ranging");strategy={"bullish":"momentum","bearish":"trend_following","ranging":"mean_reversion","volatile":"breakout"}.get(regime,"swing")
        return {"market_regime":regime,"strategy_recommendation":strategy,"confidence":.65,"reasoning_summary":"Deterministic fallback selected a strategy from regime and risk indicators.","provider":"local_fallback"}
