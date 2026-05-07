"""
Integration test for complete opportunity flow:
Creation → Scoring → Decision → Draft → Submission
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_complete_opportunity_flow(client: AsyncClient, auth_headers: dict):
    """Test complete opportunity flow from creation to submission"""
    
    # 1. Create opportunity
    opportunity_data = {
        "title": "Test Opportunity",
        "description": "A test opportunity for integration testing",
        "source_platform": "test",
        "source_url": "https://test.com/opportunity/1",
        "deadline": "2026-12-31T23:59:59Z",
        "raw_data": {
            "budget": "$5000",
            "skills": ["Python", "FastAPI"]
        }
    }
    
    response = await client.post(
        "/api/v1/opportunities",
        json=opportunity_data,
        headers=auth_headers
    )
    assert response.status_code == 200
    opportunity = response.json()
    opportunity_id = opportunity["id"]
    assert opportunity["title"] == "Test Opportunity"
    assert opportunity["status"] == "new"
    
    # 2. Score opportunity
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/score",
        headers=auth_headers
    )
    assert response.status_code == 200
    scored_opportunity = response.json()
    assert scored_opportunity["status"] == "scored"
    assert scored_opportunity["total_score"] is not None
    assert scored_opportunity["total_score"] > 0
    
    # 3. Make decision (approve)
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/decide",
        json={"decision": "approved"},
        headers=auth_headers
    )
    assert response.status_code == 200
    decided_opportunity = response.json()
    assert decided_opportunity["status"] == "approved"
    
    # 4. Generate draft
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/draft",
        headers=auth_headers
    )
    assert response.status_code == 200
    draft = response.json()
    draft_id = draft["id"]
    assert draft["opportunity_id"] == opportunity_id
    assert draft["status"] == "pending"
    assert len(draft["content"]) > 0
    
    # 5. Approve draft
    response = await client.post(
        f"/api/v1/drafts/{draft_id}/approve",
        headers=auth_headers
    )
    assert response.status_code == 200
    approved_draft = response.json()
    assert approved_draft["status"] == "approved"
    
    # 6. Create submission
    response = await client.post(
        "/api/v1/submissions",
        json={
            "opportunity_id": opportunity_id,
            "draft_id": draft_id,
            "title": "Test Submission",
            "content": approved_draft["content"]
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    submission = response.json()
    submission_id = submission["id"]
    assert submission["opportunity_id"] == opportunity_id
    assert submission["status"] == "sent"
    
    # 7. Mark submission as won
    response = await client.post(
        f"/api/v1/submissions/{submission_id}/outcome",
        json={
            "status": "won",
            "outcome_notes": "Client accepted our proposal"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    final_submission = response.json()
    assert final_submission["status"] == "won"
    
    # 8. Verify opportunity is marked as won
    response = await client.get(
        f"/api/v1/opportunities/{opportunity_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    final_opportunity = response.json()
    assert final_opportunity["status"] == "won"


@pytest.mark.asyncio
async def test_opportunity_rejection_flow(client: AsyncClient, auth_headers: dict):
    """Test opportunity rejection flow"""
    
    # 1. Create opportunity
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "title": "Low Quality Opportunity",
            "description": "This should be rejected",
            "source_platform": "test",
            "source_url": "https://test.com/opportunity/2"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    opportunity = response.json()
    opportunity_id = opportunity["id"]
    
    # 2. Score opportunity (assume low score)
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/score",
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # 3. Reject opportunity
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/decide",
        json={
            "decision": "rejected",
            "reason": "Low score, not a good fit"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    rejected_opportunity = response.json()
    assert rejected_opportunity["status"] == "rejected"
    
    # 4. Verify no draft was created
    response = await client.get(
        f"/api/v1/opportunities/{opportunity_id}/drafts",
        headers=auth_headers
    )
    assert response.status_code == 200
    drafts = response.json()
    assert len(drafts) == 0


@pytest.mark.asyncio
async def test_opportunity_list_and_filter(client: AsyncClient, auth_headers: dict):
    """Test opportunity listing and filtering"""
    
    # Create multiple opportunities
    for i in range(5):
        await client.post(
            "/api/v1/opportunities",
            json={
                "title": f"Opportunity {i}",
                "description": f"Description {i}",
                "source_platform": "test",
                "source_url": f"https://test.com/opportunity/{i}"
            },
            headers=auth_headers
        )
    
    # List all opportunities
    response = await client.get(
        "/api/v1/opportunities",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    
    # Filter by status
    response = await client.get(
        "/api/v1/opportunities?status=new",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert all(item["status"] == "new" for item in data["items"])
    
    # Pagination
    response = await client.get(
        "/api/v1/opportunities?skip=0&limit=2",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
