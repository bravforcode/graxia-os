"""Hyperoptable parameters from Freqtrade pattern"""
from dataclasses import dataclass
from typing import Any, List, Optional
import random

# Global flag for optimization mode
_optimization_mode = False

def set_optimization_mode(enabled: bool):
    global _optimization_mode
    _optimization_mode = enabled

def is_optimizing() -> bool:
    return _optimization_mode

@dataclass
class HyperParam:
    """A parameter that can be optimized by hyperopt"""
    value: Any
    low: Any
    high: Any
    space: str = "buy"
    optimize: bool = True
    step: Optional[Any] = None
    
    @property
    def current(self):
        """Returns full range during optimization, single value otherwise"""
        if is_optimizing() and self.optimize:
            if self.step is not None:
                return list(range(int(self.low), int(self.high) + 1, int(self.step)))
            return (self.low, self.high)
        return self.value
    
    def sample(self):
        """Sample a random value from the range"""
        if is_optimizing() and self.optimize:
            if isinstance(self.low, float):
                return random.uniform(self.low, self.high)
            return random.randint(int(self.low), int(self.high))
        return self.value

@dataclass
class IntParameter(HyperParam):
    """Integer parameter for optimization"""
    step: int = 1

@dataclass  
class RealParameter(HyperParam):
    """Float parameter for optimization"""
    pass

@dataclass
class CategoricalParameter(HyperParam):
    """Categorical parameter for optimization"""
    categories: List[Any] = None
    
    def sample(self):
        if is_optimizing() and self.optimize and self.categories:
            return random.choice(self.categories)
        return self.value
