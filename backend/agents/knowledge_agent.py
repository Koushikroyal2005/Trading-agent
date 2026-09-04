"""Small, HDD-friendly 128-dimensional vector knowledge store."""
from __future__ import annotations
import hashlib,json
from uuid import uuid4
from pathlib import Path
import numpy as np
from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketSnapshot

class KnowledgeAgent(BaseAgent[dict,list[dict]]):
    def __init__(self,*args,storage_path:Path,**kwargs):super().__init__("knowledge",*args,**kwargs);self.path=storage_path/"knowledge"/"scenarios.jsonl";self.path.parent.mkdir(parents=True,exist_ok=True);self.records:list[dict]=[];self.collection=None
    async def initialize(self):
        if self.path.exists():
            self.records=[json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()][-5000:]
        try:
            import chromadb
            self.collection=chromadb.PersistentClient(path=str(self.path.parent/"chroma")).get_or_create_collection("market_scenarios")
        except ImportError:pass
        await super().initialize()
    @staticmethod
    def _embedding(snapshot:MarketSnapshot)->list[float]:
        values=list(snapshot.indicators.values());seed=hashlib.sha256(snapshot.symbol.encode()).digest();vector=np.zeros(128,dtype=float)
        for i,value in enumerate(values):vector[i%128]+=float(value)/(abs(float(value))+1)
        for i,byte in enumerate(seed):vector[(i*3)%128]+=(byte/255-.5)*.05
        norm=np.linalg.norm(vector);return (vector/max(norm,1e-9)).tolist()
    async def _process(self,input_data:dict)->list[dict]:
        snapshot:MarketSnapshot=input_data["snapshot"];embedding=self._embedding(snapshot);query=np.asarray(embedding);scored=[]
        if self.collection and self.collection.count():
            result=self.collection.query(query_embeddings=[embedding],n_results=min(5,self.collection.count()))
            return [metadata|{"similarity":round(1-distance,4)} for metadata,distance in zip(result["metadatas"][0],result["distances"][0])]
        for record in self.records:scored.append((float(query@np.asarray(record["embedding"])),record))
        return [{k:v for k,v in record.items() if k!="embedding"}|{"similarity":round(score,4)} for score,record in sorted(scored,key=lambda x:x[0],reverse=True)[:5]]
    async def remember(self,snapshot:MarketSnapshot,strategy:str,outcome:float)->None:
        record={"symbol":snapshot.symbol,"regime":snapshot.regime.value,"strategy":strategy,"outcome":outcome,"embedding":self._embedding(snapshot)};self.records.append(record)
        with self.path.open("a",encoding="utf-8") as handle:handle.write(json.dumps(record,separators=(",",":"))+"\n")
        if self.collection:self.collection.add(ids=[str(uuid4())],embeddings=[record["embedding"]],metadatas=[{k:v for k,v in record.items() if k!="embedding"}])
