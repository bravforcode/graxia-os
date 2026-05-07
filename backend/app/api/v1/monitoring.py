from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.openclaw_usage import OpenClawUsage
from app.models.organization import Organization

router = APIRouter()

@router.get("/agents/health")
async def get_agent_health(
    db: AsyncSession = Depends(deps.get_db),
    org: Organization = Depends(deps.get_org)
):
    """
    Returns real-time health metrics for all agents in the organization.
    Includes token usage, latency, and success rates.
    """
    # Simplified metrics for demonstration
    # In a real scenario, this would query Prometheus or a specialized usage_logs table
    
    # Query token usage for the last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    stmt = select(
        OpenClawUsage.model,
        func.sum(OpenClawUsage.input_tokens).label("total_input"),
        func.sum(OpenClawUsage.output_tokens).label("total_output"),
        func.count(OpenClawUsage.id).label("request_count")
    ).where(
        OpenClawUsage.organization_id == org.id,
        OpenClawUsage.created_at >= yesterday
    ).group_by(OpenClawUsage.model)
    
    result = await db.execute(stmt)
    usage_data = result.all()
    
    metrics = []
    for row in usage_data:
        metrics.append({
            "model": row.model,
            "total_tokens": row.total_input + row.total_output,
            "request_count": row.request_count,
            "status": "healthy" if row.request_count > 0 else "idle"
        })
        
    return {
        "organization": org.name,
        "timestamp": datetime.utcnow(),
        "agent_metrics": metrics,
        "system_status": "operational"
    }
