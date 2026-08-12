"""
Skill Chaining API — Smart co-occurrence engine and workflow suggestions.
Features 66-70: Smart chaining, co-occurrence, UI.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skill_chaining import SkillChainUI, SkillCoOccurrenceEngine
from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.user import User

router = APIRouter(prefix="/skill-chaining", tags=["skill-chaining"])


# Request/Response Models
class ChainAnalysisRequest(BaseModel):
    days_back: int = Query(default=30, ge=1, le=90)
    min_occurrences: int = Query(default=3, ge=2)
    min_confidence: float = Query(default=0.3, ge=0.0, le=1.0)


class WorkflowSuggestionRequest(BaseModel):
    goal_description: str
    max_suggestions: int = Query(default=5, ge=1, le=10)


class CreateWorkflowRequest(BaseModel):
    skill_chain: list[str]
    workflow_name: str
    description: str


class ChainResponse(BaseModel):
    analysis_period_days: int
    total_executions: int
    unique_users: int
    co_occurrences: dict[str, Any]
    skill_chains: list[dict[str, Any]]
    top_skills: list[dict[str, Any]]
    generated_at: str


class SuggestionResponse(BaseModel):
    suggestions: list[dict[str, Any]]
    generated_at: str


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    flow_definition: dict[str, Any]


# API Endpoints
@router.get("/analyze")
async def analyze_skill_patterns(
    request: ChainAnalysisRequest,
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> ChainResponse:
    """Analyze skill execution patterns to find co-occurrences."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    engine = SkillCoOccurrenceEngine(db)
    analysis = await engine.analyze_skill_patterns(
        days_back=request.days_back,
        min_occurrences=request.min_occurrences,
        min_confidence=request.min_confidence,
    )
    
    return ChainResponse(
        analysis_period_days=analysis["analysis_period_days"],
        total_executions=analysis["total_executions"],
        unique_users=analysis["unique_users"],
        co_occurrences=analysis["co_occurrences"],
        skill_chains=analysis["skill_chains"],
        top_skills=analysis["top_skills"],
        generated_at=analysis["generated_at"],
    )


@router.get("/visualize")
async def get_chain_visualization(
    days_back: int = Query(default=30, ge=1, le=90),
    min_confidence: float = Query(default=0.3, ge=0.0, le=1.0),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get skill chain visualization data for UI."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    engine = SkillCoOccurrenceEngine(db)
    analysis = await engine.analyze_skill_patterns(
        days_back=days_back,
        min_confidence=min_confidence,
    )
    
    # Render visualization
    ui = SkillChainUI()
    diagram = ui.render_chain_diagram(analysis["skill_chains"])
    
    return {
        "diagram": diagram,
        "top_skills": analysis["top_skills"][:10],
        "analysis_period": {
            "days": days_back,
            "min_confidence": min_confidence,
        },
    }


@router.post("/suggest")
async def suggest_workflows(
    request: WorkflowSuggestionRequest,
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    """Generate workflow suggestions based on goal and skill patterns."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    engine = SkillCoOccurrenceEngine(db)
    suggestions = await engine.generate_workflow_suggestions(
        goal_description=request.goal_description,
        max_suggestions=request.max_suggestions,
    )
    
    return SuggestionResponse(
        suggestions=suggestions,
        generated_at=engine._get_current_timestamp(),
    )


@router.post("/create-workflow")
async def create_recommended_workflow(
    request: CreateWorkflowRequest,
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Create a workflow from a recommended skill chain."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    if len(request.skill_chain) < 2:
        raise HTTPException(status_code=400, detail="Skill chain must have at least 2 skills")
    
    engine = SkillCoOccurrenceEngine(db)
    workflow = await engine.create_recommended_workflow(
        user_id=str(user.id),
        skill_chain=request.skill_chain,
        workflow_name=request.workflow_name,
        description=request.description,
    )
    
    return WorkflowResponse(
        id=str(workflow.id),
        name=workflow.name,
        description=workflow.description,
        status=workflow.status,
        flow_definition=workflow.flow_definition,
    )


@router.get("/ui-components")
async def get_ui_components():
    """Get UI component definitions for skill chaining interface."""
    return {
        "chain_diagram": {
            "component": "SkillChainDiagram",
            "props": {
                "nodes": "Array<ChainNode>",
                "edges": "Array<ChainEdge>",
                "layout": "'hierarchical' | 'force'",
                "interactive": "boolean",
                "onNodeClick": "(node: ChainNode) => void",
                "onEdgeClick": "(edge: ChainEdge) => void",
            },
        },
        "suggestion_card": {
            "component": "WorkflowSuggestionCard",
            "props": {
                "suggestion": "WorkflowSuggestion",
                "onCreate": "() => void",
                "onPreview": "() => void",
                "onCustomize": "() => void",
            },
        },
        "pattern_analyzer": {
            "component": "PatternAnalyzer",
            "props": {
                "patterns": "Array<CoOccurrence>",
                "minConfidence": "number",
                "onFilterChange": "(confidence: number) => void",
            },
        },
    }


@router.get("/stats")
async def get_chaining_stats(
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get skill chaining statistics for dashboard."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    engine = SkillCoOccurrenceEngine(db)
    analysis = await engine.analyze_skill_patterns(days_back=days)
    
    # Calculate additional stats
    total_chains = len(analysis["skill_chains"])
    avg_chain_strength = sum(
        chain.get("chain_strength", 0) for chain in analysis["skill_chains"]
    ) / total_chains if total_chains > 0 else 0
    
    top_skill = analysis["top_skills"][0] if analysis["top_skills"] else None
    
    return {
        "period_days": days,
        "total_chains": total_chains,
        "average_chain_strength": avg_chain_strength,
        "strongest_chain": max(
            analysis["skill_chains"], 
            key=lambda x: x.get("chain_strength", 0)
        ) if analysis["skill_chains"] else None,
        "top_skill": top_skill,
        "co_occurrence_pairs": len(analysis["co_occurrences"]),
        "last_analyzed": analysis["generated_at"],
    }
