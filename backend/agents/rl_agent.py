"""Online 128-state policy with replay; optional Stable-Baselines3 PPO backend."""
from __future__ import annotations
import json
from collections import deque
from pathlib import Path
import numpy as np
from backend.agents.base_agent import BaseAgent
from backend.models.domain.entities import MarketSnapshot,Side

class RLAgent(BaseAgent[dict,dict]):
    def __init__(self,*args,storage_path:Path,**kwargs):super().__init__("rl",*args,**kwargs);self.path=storage_path/"models"/"rl_policy.npz";self.ppo_path=storage_path/"models"/"ppo_policy";self.path.parent.mkdir(parents=True,exist_ok=True);self.weights=np.zeros((3,128));self.buffer=deque(maxlen=10_000);self.updates=0;self.ppo=None;self.ppo_env=None
    async def initialize(self):
        if self.path.exists():self.weights=np.load(self.path)["weights"]
        try:
            import gymnasium as gym
            from gymnasium import spaces
            from stable_baselines3 import PPO
            class FeedbackEnv(gym.Env):
                def __init__(self):self.observation_space=spaces.Box(-1,1,(128,),dtype=np.float32);self.action_space=spaces.Discrete(3);self.current=np.zeros(128,dtype=np.float32);self.reward=0.0
                def reset(self,seed=None,options=None):super().reset(seed=seed);return self.current,{}
                def step(self,action):return self.current,float(self.reward),True,False,{}
            self.ppo_env=FeedbackEnv();zip_path=Path(str(self.ppo_path)+".zip");self.ppo=PPO.load(str(zip_path),env=self.ppo_env) if zip_path.exists() else PPO("MlpPolicy",self.ppo_env,verbose=0,n_steps=16,batch_size=16)
        except ImportError:pass
        await super().initialize()
    @staticmethod
    def state(snapshot:MarketSnapshot)->np.ndarray:
        vector=np.zeros(128);values=list(snapshot.indicators.values())
        for index,value in enumerate(values):vector[index%128]=float(value)/(abs(float(value))+1)
        return vector
    async def _process(self,input_data:dict)->dict:
        state=self.state(input_data["snapshot"]);scores=self.weights@state;prob=np.exp(scores-scores.max());prob/=prob.sum();index=int(np.argmax(prob))
        if self.ppo:index=int(self.ppo.predict(state.astype(np.float32),deterministic=True)[0])
        return {"action":[Side.BUY,Side.SELL,Side.HOLD][index].value,"confidence":float(prob[index]),"state_dimensions":128,"algorithm":"PPO" if self.ppo else "lightweight policy-gradient fallback"}
    async def learn(self,snapshot:MarketSnapshot,action:Side,pnl:float,sharpe:float,win_rate:float,drawdown:float,aif_score:float)->float:
        reward=pnl*10+sharpe*5+win_rate*2-drawdown*3+aif_score*.3;state=self.state(snapshot);index={Side.BUY:0,Side.SELL:1,Side.HOLD:2}[action];self.buffer.append((state,index,reward));baseline=np.mean([r[2] for r in list(self.buffer)[-100:]]);self.weights[index]+=1e-4*(reward-baseline)*state;self.updates+=1
        if self.ppo:
            self.ppo_env.current=state.astype(np.float32);self.ppo_env.reward=float(reward);self.ppo.learn(total_timesteps=16,reset_num_timesteps=False)
        np.savez_compressed(self.path,weights=self.weights)
        if self.ppo and self.updates%10==0:self.ppo.save(str(self.ppo_path))
        return float(reward)
