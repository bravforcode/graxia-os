"""Bias detection from Freqtrade pattern"""
from typing import Dict, List, Any, Optional
import logging
import math

logger = logging.getLogger(__name__)

class BiasDetector:
    """Detects recursive and lookahead bias in backtests"""
    
    def check_recursive_bias(self, indicator_func, data: Dict[str, List], 
                            candle_counts: List[int] = None) -> Dict[str, str]:
        """Compare indicator values across different warmup periods"""
        if candle_counts is None:
            candle_counts = [100, 200, 300, 500]
        
        results = {}
        for count in candle_counts:
            if len(data.get("close", [])) >= count:
                subset = {k: v[:count] for k, v in data.items()}
                results[count] = indicator_func(subset)
        
        if len(results) < 2:
            return {}
        
        biases = {}
        first_count = list(results.keys())[0]
        for key in results[first_count]:
            last_vals = []
            for c in results:
                val = results[c].get(key)
                if val is not None:
                    last_vals.append(val[-1] if isinstance(val, list) and val else val)
            if len(last_vals) >= 2 and not all(math.isclose(v, last_vals[0], rel_tol=1e-6, abs_tol=1e-9) for v in last_vals):
                biases[key] = "RECURSIVE"
        
        return biases
    
    def check_lookahead_bias(self, indicator_func, data: Dict[str, List], 
                            split_index: int) -> Dict[str, str]:
        """Check if indicators use future data by comparing full vs truncated runs"""
        if split_index <= 0 or split_index >= len(data.get("close", [])):
            return {}
        
        # Full run
        full_result = indicator_func(data)
        
        # Truncated run (up to split_index)
        truncated = {k: v[:split_index] for k, v in data.items()}
        trunc_result = indicator_func(truncated)
        
        biases = {}
        for key in full_result:
            if key in trunc_result:
                full_val = full_result[key]
                trunc_val = trunc_result[key]
                
                # Compare only the overlapping portion for list/array values
                if isinstance(full_val, list) and isinstance(trunc_val, list):
                    # Only compare up to the length of the truncated result
                    overlap = full_val[:len(trunc_val)]
                    # Use approximate comparison for floats (IEEE 754 precision)
                    if not all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9) for a, b in zip(overlap, trunc_val)):
                        biases[key] = "LOOKAHEAD"
                elif not isinstance(full_val, list) and not isinstance(trunc_val, list):
                    # Scalar comparison with epsilon
                    if not math.isclose(float(full_val), float(trunc_val), rel_tol=1e-6, abs_tol=1e-9):
                        biases[key] = "LOOKAHEAD"
        
        return biases
