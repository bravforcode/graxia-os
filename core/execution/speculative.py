import asyncio
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from core.providers.base import BaseLLMProvider
from core.logger import logger

class SpeculativeStep(BaseModel):
    """A single step in a multi-step task."""
    id: int
    task: str
    draft: Optional[str] = None
    verification: Optional[str] = None
    final_output: Optional[str] = None
    is_valid: bool = False

class SpeculativeExecutor:
    """
    Speculative Execution Engine.
    Drafts multiple steps in parallel using a 'Fast' model and 
    verifies/corrects them using a 'Flagship' model.
    """
    
    def __init__(self, fast_llm: BaseLLMProvider, flagship_llm: BaseLLMProvider):
        self.fast_llm = fast_llm
        self.flagship_llm = flagship_llm

    async def execute_task(self, main_task: str, sub_tasks: List[str]) -> List[SpeculativeStep]:
        """
        Executes a multi-step task speculatively.
        """
        logger.info(f"Starting speculative execution for task: {main_task[:50]}...")
        
        steps = [SpeculativeStep(id=i, task=task) for i, task in enumerate(sub_tasks)]
        
        # Phase 1: Parallel Drafting (Fast Model)
        logger.info(f"Phase 1: Drafting {len(steps)} steps in parallel using fast model...")
        draft_tasks = [self._draft_step(step) for step in steps]
        await asyncio.gather(*draft_tasks)
        
        # Phase 2: Sequential/Batch Verification (Flagship Model)
        # We use Flagship model to verify the draft and the context of previous steps
        logger.info("Phase 2: Verifying and correcting steps using flagship model...")
        
        for i in range(len(steps)):
            step = steps[i]
            context = "\n".join([f"Step {s.id}: {s.final_output}" for s in steps[:i]])
            
            verification_prompt = f"""
            MAIN TASK: {main_task}
            PREVIOUS STEPS CONTEXT:
            {context}
            
            CURRENT STEP TASK: {step.task}
            FAST MODEL DRAFT: {step.draft}
            
            INSTRUCTION: Verify the draft for the current step. 
            If it's correct and fits the context, repeat it. 
            If it's incorrect or missing details, correct it.
            Provide the final verified output for this step.
            """
            
            try:
                response = await self.flagship_llm.generate_response(verification_prompt)
                step.final_output = response["content"]
                step.is_valid = True
                logger.info(f"Step {step.id} verified/corrected.")
            except Exception as e:
                logger.error(f"Error verifying step {step.id}: {str(e)}")
                step.final_output = step.draft # Fallback to draft
        
        logger.info("Speculative execution complete.")
        return steps

    async def _draft_step(self, step: SpeculativeStep):
        """Internal helper to draft a single step."""
        prompt = f"Draft a detailed implementation or response for this task: {step.task}"
        try:
            response = await self.fast_llm.generate_response(prompt)
            step.draft = response["content"]
        except Exception as e:
            logger.error(f"Error drafting step {step.id}: {str(e)}")
            step.draft = "[DRAFT FAILED]"
