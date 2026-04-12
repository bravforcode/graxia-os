"""
COG Evolution Agent — Weekly evolution loop that analyzes vault patterns
and suggests scoring weight adjustments.

This agent:
1. Scans vault notes for tag patterns
2. Analyzes them with LLM
3. Suggests weight adjustments (never auto-applies)
4. Emits cog.evolution_suggested event for approval
"""

import logging
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


def extract_vault_tag_frequencies(vault_path: Path) -> dict[str, int]:
    """
    Walk vault and count tag frequencies from frontmatter.

    Args:
        vault_path: Path to vault root

    Returns:
        dict mapping tag names to occurrence counts
    """
    from app.integrations.obsidian import parse_frontmatter

    frequencies: dict[str, int] = {}

    # Walk all markdown files
    for md_file in vault_path.rglob("*.md"):
        try:
            frontmatter_data = parse_frontmatter(md_file)
            # Extract tags from frontmatter
            tags = frontmatter_data.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str):
                        frequencies[tag] = frequencies.get(tag, 0) + 1
        except Exception as e:
            logger.debug(f"Failed to parse {md_file}: {e}")
            continue

    return frequencies


def build_pattern_context(frequencies: dict[str, int], top_n: int = 15) -> str:
    """
    Format tag frequencies into LLM context string.

    Args:
        frequencies: dict mapping tags to counts
        top_n: number of top tags to include

    Returns:
        formatted string for LLM prompt
    """
    # Sort by frequency descending
    sorted_tags = sorted(frequencies.items(), key=lambda x: x[1], reverse=True)
    top_tags = sorted_tags[:top_n]

    if not top_tags:
        return "No tags found in vault."

    lines = ["Top vault tags by frequency:", ""]
    for tag, count in top_tags:
        lines.append(f"  - {tag}: {count} notes")

    return "\n".join(lines)


class CogEvolutionAgent(BaseAgent):
    """
    Weekly evolution loop that analyzes vault patterns and suggests
    scoring weight adjustments.
    """

    name = "cog_evolution"

    async def run_weekly_evolution(self, vault_path: str) -> None:
        """
        Scan vault patterns, analyze with LLM, suggest weight adjustments.

        Never auto-applies weights — emits event for approval.

        Args:
            vault_path: Path to vault root directory
        """
        logger.info(f"Starting weekly COG evolution for vault: {vault_path}")

        try:
            vault = Path(vault_path)
            if not vault.exists():
                logger.error(f"Vault path does not exist: {vault_path}")
                await self.log_audit(
                    action="cog_evolution",
                    details={"vault_path": vault_path, "status": "vault_not_found"},
                    success=False,
                    error="Vault path does not exist"
                )
                return

            # Validate that path is a directory
            if not vault.is_dir():
                logger.error("vault_path_not_directory", extra={"vault_path": str(vault)})
                await self.log_audit(
                    action="cog_evolution",
                    details={"vault_path": vault_path, "status": "vault_path_not_directory"},
                    success=False,
                    error="vault_path_not_directory"
                )
                return

            # Step 1: Extract tag frequencies
            frequencies = extract_vault_tag_frequencies(vault)
            logger.info(f"Found {len(frequencies)} unique tags in vault")

            if not frequencies:
                logger.info("No tags found in vault, skipping evolution")
                await self.log_audit(
                    action="cog_evolution",
                    details={"vault_path": vault_path, "status": "no_tags"},
                    success=True,
                )
                return

            # Step 2: Build context
            pattern_context = build_pattern_context(frequencies, top_n=15)

            # Step 3: Call LLM to analyze and suggest weights
            suggested_weights = await self._analyze_patterns_with_llm(pattern_context)

            if not suggested_weights:
                logger.warning("LLM failed to suggest weights")
                await self.log_audit(
                    action="cog_evolution",
                    details={"vault_path": vault_path, "status": "llm_failed"},
                    success=False,
                    error="LLM failed to suggest weights"
                )
                return

            # Step 4: Emit event for approval (never auto-apply)
            await self.bus.emit("cog.evolution_suggested", {
                "vault_path": vault_path,
                "tag_frequencies": frequencies,
                "suggested_weights": suggested_weights,
                "confidence": suggested_weights.get("confidence", 0.5),
                "reasoning": suggested_weights.get("reasoning", ""),
            })

            logger.info(f"Evolution suggestion emitted with confidence {suggested_weights.get('confidence', 0)}")
            await self.log_audit(
                action="cog_evolution",
                details={
                    "vault_path": vault_path,
                    "status": "suggested",
                    "tag_count": len(frequencies),
                    "confidence": suggested_weights.get("confidence", 0),
                },
                success=True,
            )

        except Exception as e:
            logger.error(f"COG evolution failed: {e}", exc_info=True)
            await self.log_audit(
                action="cog_evolution",
                details={"vault_path": vault_path, "status": "error"},
                success=False,
                error=str(e)
            )

    async def _analyze_patterns_with_llm(self, pattern_context: str) -> dict[str, Any] | None:
        """
        Use LLM to analyze vault patterns and suggest weight adjustments.

        Returns JSON with suggested weights and confidence score.
        """
        system_prompt = """You are a scoring weight optimizer for professional opportunities.

Analyze the vault tags to understand what the user focuses on, then suggest
adjustments to these scoring weights:
- money_score: financial opportunity (0.0-1.0)
- brand_score: brand value and positioning (0.0-1.0)
- network_score: network expansion potential (0.0-1.0)
- startup_score: startup/product fit (0.0-1.0)
- effort_score: effort/complexity (0.0-1.0)

Respond with JSON only, no extra text:
{
  "suggested_weights": {
    "money_score": 0.25,
    "brand_score": 0.20,
    "network_score": 0.20,
    "startup_score": 0.20,
    "effort_score": 0.15
  },
  "confidence": 0.75,
  "reasoning": "Based on tag frequencies showing focus on X, Y, Z..."
}"""

        user_prompt = f"""Analyze these vault tag patterns and suggest weight adjustments:

{pattern_context}

Remember: all weights must sum to approximately 1.0. Return JSON only."""

        try:
            # Use complete_json() which handles parsing, markdown cleanup, and error handling
            result = await self.llm.complete_json(
                system=system_prompt,
                user=user_prompt,
                max_tokens=600,
                task_class="scoring_optimization",
            )
            return result

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return None
