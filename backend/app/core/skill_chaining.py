"""
Smart Skill Chaining — Co-occurrence Engine
Analyzes skill usage patterns to recommend optimal skill chains.
Features 66-70: Smart chaining, co-occurrence, UI.
"""

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_log import UsageLog
from app.models.workflow import Workflow

logger = logging.getLogger(__name__)


class SkillCoOccurrenceEngine:
    """Analyzes skill execution patterns to build intelligent chains."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def analyze_skill_patterns(
        self,
        days_back: int = 30,
        min_occurrences: int = 3,
        min_confidence: float = 0.3
    ) -> dict[str, Any]:
        """Analyze skill execution patterns to find co-occurrences."""
        cutoff_date = datetime.now(UTC) - timedelta(days=days_back)
        
        # Get skill execution sequences
        result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.feature == "skill_execution")
            .where(UsageLog.created_at >= cutoff_date)
            .where(UsageLog.meta["skill_name"].isnot(None))
            .order_by(UsageLog.created_at, UsageLog.user_id)
        )
        
        executions = result.scalars().all()
        
        # Build sequences per user/session
        user_sequences = defaultdict(list)
        for exec in executions:
            user_id = exec.user_id
            skill_name = exec.meta.get("skill_name")
            if skill_name:
                user_sequences[user_id].append(skill_name)
        
        # Analyze co-occurrences
        co_occurrences = Counter()
        skill_sequences = defaultdict(list)
        
        for user_id, skills in user_sequences.items():
            # Find skill pairs that occur together
            for i in range(len(skills) - 1):
                current_skill = skills[i]
                next_skill = skills[i + 1]
                pair = f"{current_skill} -> {next_skill}"
                co_occurrences[pair] += 1
                
                # Track sequences for chain analysis
                if len(skills) >= 3:
                    sequence = tuple(skills[i:i+3])
                    skill_sequences[current_skill].append(sequence)
        
        # Filter by minimum occurrences
        filtered_pairs = {
            pair: count for pair, count in co_occurrences.items()
            if count >= min_occurrences
        }
        
        # Calculate confidence scores
        total_pairs = sum(co_occurrences.values())
        confidence_scores = {
            pair: count / total_pairs for pair, count in filtered_pairs.items()
        }
        
        # Filter by confidence
        high_confidence_pairs = {
            pair: {
                "occurrences": count,
                "confidence": confidence
            }
            for pair, count, confidence in [
                (pair, count, conf) for pair, count in filtered_pairs.items()
                for conf in [confidence_scores.get(pair, 0)]
            ]
            if confidence >= min_confidence
        }
        
        # Build skill chains
        skill_chains = self._build_skill_chains(skill_sequences, high_confidence_pairs)
        
        return {
            "analysis_period_days": days_back,
            "total_executions": len(executions),
            "unique_users": len(user_sequences),
            "co_occurrences": high_confidence_pairs,
            "skill_chains": skill_chains,
            "top_skills": self._get_top_skills(executions),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    
    def _build_skill_chains(
        self,
        skill_sequences: dict[str, list[tuple[str, ...]]],
        co_occurrences: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build skill chains from sequences and co-occurrences."""
        chains = []
        
        for skill, sequences in skill_sequences.items():
            if not sequences:
                continue
            
            # Count sequence patterns
            sequence_counts = Counter(sequences)
            most_common_sequence = sequence_counts.most_common(1)[0][0]
            
            # Get co-occurrence partners
            partners = []
            for pair, data in co_occurrences.items():
                if pair.startswith(f"{skill} -> "):
                    next_skill = pair.split(" -> ")[1]
                    partners.append({
                        "skill": next_skill,
                        "confidence": data["confidence"],
                        "occurrences": data["occurrences"],
                    })
                elif pair.endswith(f" -> {skill}"):
                    prev_skill = pair.split(" -> ")[0]
                    partners.append({
                        "skill": prev_skill,
                        "confidence": data["confidence"],
                        "occurrences": data["occurrences"],
                    })
            
            # Sort partners by confidence
            partners.sort(key=lambda x: x["confidence"], reverse=True)
            
            chains.append({
                "root_skill": skill,
                "most_common_sequence": list(most_common_sequence),
                "sequence_count": sequence_counts[most_common_sequence],
                "linked_skills": partners[:5],  # Top 5 partners
                "chain_strength": self._calculate_chain_strength(partners),
            })
        
        # Sort chains by strength
        chains.sort(key=lambda x: x["chain_strength"], reverse=True)
        return chains
    
    def _calculate_chain_strength(self, partners: list[dict[str, Any]]) -> float:
        """Calculate overall chain strength based on partner confidence."""
        if not partners:
            return 0.0
        
        # Weight by position (first partner has more weight)
        total_strength = 0.0
        for i, partner in enumerate(partners):
            weight = 1.0 / (i + 1)  # Decreasing weight
            total_strength += partner["confidence"] * weight
        
        return total_strength
    
    def _get_top_skills(self, executions: list[UsageLog]) -> list[dict[str, Any]]:
        """Get most frequently used skills."""
        skill_counts = Counter()
        skill_success = defaultdict(lambda: {"success": 0, "total": 0})
        
        for exec in executions:
            skill_name = exec.meta.get("skill_name")
            if skill_name:
                skill_counts[skill_name] += 1
                
                success = exec.meta.get("success", True)
                skill_success[skill_name]["total"] += 1
                if success:
                    skill_success[skill_name]["success"] += 1
        
        # Calculate success rates
        top_skills = []
        for skill, count in skill_counts.most_common(10):
            stats = skill_success[skill]
            success_rate = (stats["success"] / stats["total"]) if stats["total"] > 0 else 1.0
            
            top_skills.append({
                "skill_name": skill,
                "usage_count": count,
                "success_rate": success_rate,
                "total_executions": stats["total"],
                "successful_executions": stats["success"],
            })
        
        return top_skills
    
    async def generate_workflow_suggestions(
        self,
        goal_description: str,
        max_suggestions: int = 5
    ) -> list[dict[str, Any]]:
        """Generate workflow suggestions based on skill co-occurrence patterns."""
        patterns = await self.analyze_skill_patterns()
        
        # Simple keyword matching for demo (in production, use NLP)
        goal_lower = goal_description.lower()
        keywords = {
            "email": ["email", "send", "notify", "contact"],
            "analysis": ["analyze", "review", "check", "audit"],
            "automation": ["automate", "schedule", "trigger"],
            "data": ["extract", "parse", "process", "transform"],
            "integration": ["connect", "sync", "link", "bridge"],
        }
        
        # Match goal to skill categories
        matched_categories = []
        for category, words in keywords.items():
            if any(word in goal_lower for word in words):
                matched_categories.append(category)
        
        # Get relevant chains based on matched categories
        suggestions = []
        for chain in patterns["skill_chains"][:max_suggestions]:
            # Check if chain matches any category
            chain_skills = [chain["root_skill"]] + [p["skill"] for p in chain["linked_skills"]]
            chain_text = " ".join(chain_skills).lower()
            
            relevance_score = 0
            for category in matched_categories:
                if category in chain_text:
                    relevance_score += 1
            
            if relevance_score > 0 or not matched_categories:  # Include if no specific match
                suggestions.append({
                    "workflow_name": f"{chain['root_skill']} Chain",
                    "description": f"Automated workflow starting with {chain['root_skill']}",
                    "estimated_steps": len(chain["linked_skills"]) + 1,
                    "confidence": chain["chain_strength"],
                    "skills": chain_skills,
                    "relevance_score": relevance_score,
                    "sequence": [chain["root_skill"]] + [p["skill"] for p in chain["linked_skills"][:3]],
                })
        
        # Sort by confidence and relevance
        suggestions.sort(key=lambda x: (x["confidence"] + x["relevance_score"]), reverse=True)
        return suggestions[:max_suggestions]
    
    async def create_recommended_workflow(
        self,
        user_id: str,
        skill_chain: list[str],
        workflow_name: str,
        description: str
    ) -> Workflow:
        """Create a workflow from a recommended skill chain."""
        # Build workflow definition
        nodes = []
        edges = []
        
        for i, skill in enumerate(skill_chain):
            node_id = f"skill_{i}"
            nodes.append({
                "id": node_id,
                "type": "skill",
                "data": {
                    "skill_name": skill,
                    "position": {"x": i * 200, "y": 100},
                },
            })
            
            if i > 0:
                edges.append({
                    "from": f"skill_{i-1}",
                    "to": node_id,
                    "type": "success",
                })
        
        workflow = Workflow(
            workflow_key=f"auto_chain_{workflow_name.lower().replace(' ', '_')}",
            name=workflow_name,
            description=description,
            workflow_type="automation",
            flow_definition={
                "nodes": nodes,
                "edges": edges,
            },
            status="draft",
        )
        
        self.db.add(workflow)
        await self.db.flush()
        return workflow


class SkillChainUI:
    """UI components for skill chaining visualization."""
    
    @staticmethod
    def render_chain_diagram(chains: list[dict[str, Any]]) -> dict[str, Any]:
        """Render skill chain as a flow diagram."""
        nodes = []
        edges = []
        
        for i, chain in enumerate(chains):
            # Root node
            root_id = f"chain_{i}_root"
            nodes.append({
                "id": root_id,
                "type": "skill",
                "position": {"x": 50, "y": 100 + i * 150},
                "data": {
                    "label": chain["root_skill"],
                    "confidence": chain["chain_strength"],
                    "usage_count": chain.get("sequence_count", 0),
                },
            })
            
            # Partner nodes
            for j, partner in enumerate(chain["linked_skills"][:3]):  # Limit to 3 for UI
                partner_id = f"chain_{i}_partner_{j}"
                nodes.append({
                    "id": partner_id,
                    "type": "skill",
                    "position": {"x": 300 + j * 150, "y": 100 + i * 150},
                    "data": {
                        "label": partner["skill"],
                        "confidence": partner["confidence"],
                        "occurrences": partner["occurrences"],
                    },
                })
                
                edges.append({
                    "from": root_id,
                    "to": partner_id,
                    "type": "co-occurs",
                    "data": {
                        "confidence": partner["confidence"],
                        "label": f"{partner['occurrences']} times",
                    },
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "layout": "hierarchical",
        }
    
    @staticmethod
    def render_suggestion_card(suggestion: dict[str, Any]) -> dict[str, Any]:
        """Render a workflow suggestion as a UI card."""
        return {
            "id": f"suggestion_{suggestion['workflow_name'].lower().replace(' ', '_')}",
            "type": "workflow_suggestion",
            "title": suggestion["workflow_name"],
            "description": suggestion["description"],
            "skills": suggestion["skills"],
            "estimated_steps": suggestion["estimated_steps"],
            "confidence": suggestion["confidence"],
            "relevance": suggestion["relevance_score"],
            "actions": [
                {
                    "type": "create_workflow",
                    "label": "Create Workflow",
                    "primary": True,
                },
                {
                    "type": "preview_chain",
                    "label": "Preview Chain",
                },
                {
                    "type": "customize",
                    "label": "Customize",
                },
            ],
        }
