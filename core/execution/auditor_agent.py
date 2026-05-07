import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.providers.llm_client import llm_client

logger = logging.getLogger(__name__)

class PythonAuditor:
    """
    Specialized audit engine for Python codebases using the Structured Review Protocol.
    """
    def __init__(self, target_path: str):
        self.target_path = Path(target_path).absolute()
        self.max_chars_per_batch = 50000 # Roughly 15k-20k tokens to fit in context comfortably
        
    def _get_python_files(self) -> List[Path]:
        if self.target_path.is_file():
            if self.target_path.suffix == ".py":
                return [self.target_path]
            return []
        return list(self.target_path.glob("**/*.py"))

    async def _process_batches(self, files: List[Path]) -> List[str]:
        batches = []
        current_batch = []
        current_size = 0
        
        for file in files:
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                # Use relative path for context
                try:
                    rel_path = file.relative_to(self.target_path if self.target_path.is_dir() else self.target_path.parent)
                except ValueError:
                    rel_path = file.name
                    
                file_repr = f"--- File: {rel_path} ---\n{content}\n"
                if current_size + len(file_repr) > self.max_chars_per_batch and current_batch:
                    batches.append("\n".join(current_batch))
                    current_batch = [file_repr]
                    current_size = len(file_repr)
                else:
                    current_batch.append(file_repr)
                    current_size += len(file_repr)
            except Exception as e:
                logger.error(f"Failed to read {file}: {e}")
                
        if current_batch:
            batches.append("\n".join(current_batch))
            
        return batches

    async def run_audit(self) -> str:
        files = self._get_python_files()
        if not files:
            return "# Graxia Executive Audit Report\n\nNo Python assets identified for analysis."

        batches = await self._process_batches(files)
        
        # Persona 1: Drafter (Lead Architect)
        batch_drafts = []
        for i, batch_content in enumerate(batches):
            logger.info(f"Analyzing technical assets (Batch {i+1}/{len(batches)})...")
            drafter_prompt = (
                "You are a Lead Systems Architect. Your objective is to perform a deep-tissue analysis of the provided Python source code. "
                "Identify core architectural patterns, logic flow, and immediate structural risks. "
                "Maintain a highly professional, clinical, and objective tone. "
                f"Processing batch {i+1} of {len(batches)}."
            )
            draft = await llm_client.generate_completion(
                system_prompt=drafter_prompt,
                user_prompt=f"Source Code Assets (Batch {i+1}):\n\n{batch_content}",
                agent_name="auditor-lead-architect"
            )
            batch_drafts.append(draft)

        combined_draft = "\n\n".join(batch_drafts)
        
        # Persona 2: Security Expert (Cybersecurity Strategist)
        logger.info("Evaluating strategic security posture...")
        security_prompt = (
            "You are a Senior Cybersecurity Strategist. Review the architectural analysis of a codebase. "
            "Evaluate the Strategic Security Posture, focusing on sophisticated attack vectors, data integrity risks, "
            "and OWASP Enterprise compliance. Identify subtle vulnerabilities that automated scanners miss. "
            "Prioritize findings based on potential business impact."
        )
        security_critique = await llm_client.generate_completion(
            system_prompt=security_prompt,
            user_prompt=f"Architectural Analysis Draft:\n{combined_draft}",
            agent_name="auditor-security-strategist"
        )

        # Persona 3: Performance Optimizer (Efficiency Engineer)
        logger.info("Assessing operational efficiency...")
        performance_prompt = (
            "You are a Principal Efficiency Engineer. Review the architectural analysis. "
            "Analyze Operational Performance Integrity, focusing on computational latency, memory footprint optimization, "
            "and high-concurrency Pythonic idioms. Propose refinements that enhance scalability and cost-efficiency."
        )
        performance_critique = await llm_client.generate_completion(
            system_prompt=performance_prompt,
            user_prompt=f"Architectural Analysis Draft:\n{combined_draft}",
            agent_name="auditor-efficiency-engineer"
        )

        # Persona 4: Final Validator (Prestige Auditor)
        logger.info("Synthesizing prestige audit report...")
        validator_prompt = (
            "You are the Prestige Auditor. Your task is to synthesize the architect's analysis and the expert critiques "
            "into a bespoke, executive-tier Security & Performance Audit Report. The report must feel like a premium service "
            "from a top-tier global consulting firm. Use formal, sophisticated language.\n\n"
            "The report MUST adhere to this high-status structure:\n"
            "# Graxia Executive Audit: Technical Asset Evaluation\n"
            "## I. Strategic Executive Summary\n"
            "## II. Security Posture & Vulnerability Assessment (Critical/High/Medium/Low)\n"
            "## III. Operational Efficiency & Performance Refinements\n"
            "## IV. Architectural Integrity Score (0-100) & Strategic Conclusion"
        )
        
        final_report = await llm_client.generate_completion(
            system_prompt=validator_prompt,
            user_prompt=(
                f"Core Analysis:\n{combined_draft}\n\n"
                f"Security Strategy Critique:\n{security_critique}\n\n"
                f"Performance Efficiency Critique:\n{performance_critique}"
            ),
            agent_name="auditor-prestige-validator"
        )
        
        return final_report
