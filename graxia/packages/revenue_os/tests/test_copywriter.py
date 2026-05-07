"""
Test AI Copywriter
Verify Claude-powered copywriting functionality
"""
import pytest

from ..core.copywriter import Copywriter


@pytest.mark.asyncio
async def test_copywriter_initialization(mock_anthropic_client):
    """Test copywriter initialization."""
    copywriter = Copywriter(client=mock_anthropic_client)
    
    assert copywriter.client is not None
    assert copywriter.model == "claude-sonnet-4.6"


@pytest.mark.asyncio
async def test_generate_sales_email(mock_anthropic_client):
    """Test generating a sales email."""
    copywriter = Copywriter(client=mock_anthropic_client)
    
    lead_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "company": "Example Corp",
        "pain_point": "Manual data entry",
    }
    
    product_data = {
        "name": "AutoFlow",
        "value_prop": "Automate your workflows",
        "price": "$99/month",
    }
    
    result = await copywriter.generate_sales_email(
        lead_data=lead_data,
        product_data=product_data,
        tone="professional",
    )
    
    assert "html" in result
    assert "text" in result
    assert "tokens_used" in result
    assert result["tokens_used"]["input"] > 0
    assert result["tokens_used"]["output"] > 0


@pytest.mark.asyncio
async def test_generate_proposal(mock_anthropic_client):
    """Test generating a service proposal."""
    copywriter = Copywriter(client=mock_anthropic_client)
    
    client_data = {
        "name": "Jane Smith",
        "company": "Tech Startup Inc",
        "industry": "SaaS",
    }
    
    service_data = {
        "name": "Custom Integration",
        "scope": "Connect CRM to accounting system",
        "timeline": "4 weeks",
        "price": "$5,000",
    }
    
    result = await copywriter.generate_proposal(
        client_data=client_data,
        service_data=service_data,
    )
    
    assert "html" in result
    assert "text" in result
    assert "tokens_used" in result


@pytest.mark.asyncio
async def test_copywriter_tracks_tokens(mock_anthropic_client):
    """Test that copywriter tracks token usage."""
    copywriter = Copywriter(client=mock_anthropic_client)
    
    lead_data = {"name": "Test", "email": "test@example.com"}
    product_data = {"name": "Product", "value_prop": "Value"}
    
    result = await copywriter.generate_sales_email(
        lead_data=lead_data,
        product_data=product_data,
    )
    
    # Mock client returns 100 input tokens, 200 output tokens
    assert result["tokens_used"]["input"] == 100
    assert result["tokens_used"]["output"] == 200
    assert result["tokens_used"]["total"] == 300


@pytest.mark.asyncio
async def test_copywriter_different_tones(mock_anthropic_client):
    """Test generating emails with different tones."""
    copywriter = Copywriter(client=mock_anthropic_client)
    
    lead_data = {"name": "Test", "email": "test@example.com"}
    product_data = {"name": "Product", "value_prop": "Value"}
    
    tones = ["professional", "casual", "urgent"]
    
    for tone in tones:
        result = await copywriter.generate_sales_email(
            lead_data=lead_data,
            product_data=product_data,
            tone=tone,
        )
        
        assert "html" in result
        assert "text" in result
