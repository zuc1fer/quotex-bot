from .base import Strategy
from .sma_cross import SmaCrossStrategy
from .rsi import RsiStrategy
from .revert import RevertStrategy

# Registry so scripts can pick a strategy by name.
REGISTRY = {
    "sma_cross": SmaCrossStrategy,
    "rsi": RsiStrategy,
    "revert": RevertStrategy,
}

__all__ = [
    "Strategy", "SmaCrossStrategy", "RsiStrategy", "RevertStrategy", "REGISTRY",
]
