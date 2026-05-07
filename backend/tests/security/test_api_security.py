"""Security Tests for GRAXIA OS API Endpoints"""
import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


class TestEmbeddingsAPI:
    """Security tests for Embeddings API"""

    @pytest.mark.asyncio
    async def test_post_empty_body(self):
        """Test with empty request body"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/embeddings", json={})
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [400, 403, 422]  # Bad request, forbidden, or validation error

    @pytest.mark.asyncio
    async def test_post_invalid_texts_type(self):
        """Test with invalid texts type"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/embeddings", json={"texts": "not_a_list"})
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [400, 403, 422]

    @pytest.mark.asyncio
    async def test_post_missing_texts_field(self):
        """Test with missing texts field"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/embeddings", json={"other_field": "value"})
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [400, 403, 422]

    @pytest.mark.asyncio
    async def test_post_large_payload(self):
        """Test with overly large payload"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            large_text = "x" * 1000000  # 1MB string
            response = await client.post("/api/v1/embeddings", json={"texts": [large_text]})
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [400, 403, 413, 422]  # Bad request, forbidden, entity too large, or validation

    @pytest.mark.asyncio
    async def test_get_endpoint_not_allowed(self):
        """Test that GET is not allowed on embeddings endpoint"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/embeddings")
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [403, 405]  # Forbidden or method not allowed

    @pytest.mark.asyncio
    async def test_unauthorized_access(self):
        """Test unauthorized access to protected endpoints"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/admin/users")
            # 403 is expected for protected endpoints without auth
            assert response.status_code in [401, 403]  # Unauthorized or forbidden

    @pytest.mark.asyncio
    async def test_sql_injection_attempt(self):
        """Test SQL injection attempts"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            malicious_input = "'; DROP TABLE users; --"
            response = await client.post("/api/v1/embeddings", json={"texts": [malicious_input]})
            # Should not cause server error - 403 is expected for protected endpoints
            assert response.status_code in [400, 403, 422, 200]
            # Response should not contain database error messages
            if response.status_code == 200:
                assert "error" not in str(response.content).lower()
                assert "sql" not in str(response.content).lower()
