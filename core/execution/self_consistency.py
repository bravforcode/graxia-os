import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from collections import Counter
from ..providers.base import BaseLLMProvider

class ConsistencyResult(BaseModel):
    response: str
    confidence_score: float
    agreement_ratio: str  # e.g., "3/3", "2/3"
    needs_escalation: bool = False

class SelfConsistencyRouter:
    """
    Implements Self-Consistency (CoT-SC) for critical decision points.
    Samples multiple reasoning paths and selects the most frequent answer.
    """
    def __init__(self, samples: int = 3):
        self.samples = samples

    def route(self, outputs: List[str]) -> ConsistencyResult:
        """
        Analyzes sampled responses to find the majority consensus.
        """
        if not outputs:
            raise ValueError("No outputs provided for consistency check.")

        counts = Counter(outputs)
        most_common_response, count = counts.most_common(1)[0]
        
        ratio_str = f"{count}/{len(outputs)}"
        confidence = count / len(outputs)
        
        needs_escalation = False
        if len(outputs) >= 3:
            if count == 1: # 1/1/1 split
                needs_escalation = True
        elif len(outputs) == 2:
            if count == 1: # 1/1 split
                needs_escalation = True

        return ConsistencyResult(
            response=most_common_response,
            confidence_score=confidence,
            agreement_ratio=ratio_str,
            needs_escalation=needs_escalation
        )

    async def run_parallel_sampling(self, prompt: str, llm: BaseLLMProvider, temperature: float = 0.7) -> ConsistencyResult:
        """
        Calls the LLM N times in parallel with diverse reasoning paths.
        """
        tasks = [
            llm.generate_response(prompt, temperature=temperature)
            for _ in range(self.samples)
        ]
        responses = await asyncio.gather(*tasks)
        outputs = [r["content"] for r in responses]
        return self.route(outputs)
