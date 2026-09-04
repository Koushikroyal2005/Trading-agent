from backend.strategies.base import StrategyRegistry
from backend.strategies.breakout import BreakoutStrategy
from backend.strategies.mean_reversion import MeanReversionStrategy
from backend.strategies.momentum import MomentumStrategy
from backend.strategies.swing import SwingStrategy
from backend.strategies.trend_following import TrendFollowingStrategy

def default_registry() -> StrategyRegistry:
    registry=StrategyRegistry()
    for strategy in (MomentumStrategy(),MeanReversionStrategy(),BreakoutStrategy(),TrendFollowingStrategy(),SwingStrategy()):registry.register(strategy)
    return registry

__all__=["StrategyRegistry","default_registry"]
