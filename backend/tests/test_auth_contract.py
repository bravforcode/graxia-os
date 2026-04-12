import pytest


@pytest.mark.asyncio
async def test_register_login_me_and_refresh_contract(public_async_client):
    register_response = await public_async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "operator@example.com",
            "password": "correct-horse-battery",
            "full_name": "System Operator",
        },
    )

    assert register_response.status_code == 201
    registered = register_response.json()
    assert registered["token_type"] == "bearer"
    assert registered["access_token"]
    assert registered["refresh_token"]
    assert registered["user"]["email"] == "operator@example.com"
    assert registered["user"]["role"] == "user"
    assert register_response.cookies.get("access_token")
    assert register_response.cookies.get("refresh_token")
    assert register_response.cookies.get("csrf_token")

    public_async_client.headers["X-CSRF-Token"] = register_response.cookies.get("csrf_token") or ""
    me_response = await public_async_client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "operator@example.com"

    login_response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "operator@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
    logged_in = login_response.json()
    assert logged_in["access_token"]
    assert logged_in["refresh_token"]
    assert logged_in["user"]["email"] == "operator@example.com"

    refresh_response = await public_async_client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["token_type"] == "bearer"
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(public_async_client):
    payload = {"email": "duplicate@example.com", "password": "duplicate-pass"}

    first_response = await public_async_client.post("/api/v1/auth/register", json=payload)
    second_response = await public_async_client.post("/api/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Email already registered"


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(public_async_client):
    await public_async_client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "valid-password"},
    )

    response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
