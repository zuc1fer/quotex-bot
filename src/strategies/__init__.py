from .base import Strategy
from .sma_cross import SmaCrossStrategy
from .rsi import RsiStrategy

# Registry so scripts can pick a strategy by name.
REGISTRY = {
    "sma_cross": SmaCrossStrategy,
    "rsi": RsiStrategy,
}

__all__ = ["Strategy", "SmaCrossStrategy", "RsiStrategy", "REGISTRY"]
