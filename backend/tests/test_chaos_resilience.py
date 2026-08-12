import pytest
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState


def test_circuit_breaker_opens_and_blocks_calls() -> None:
    breaker = CircuitBreaker(
        name="test_sync",
        failure_threshold=2,
        recovery_timeout=60,
        expected_exception=ValueError,
    )

    def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        breaker.call(boom)
    assert breaker.state == CircuitState.CLOSED

    with pytest.raises(ValueError):
        breaker.call(boom)
    assert breaker.state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerError):
        breaker.call(lambda: 1)


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_after_timeout_for_async_calls() -> None:
    breaker = CircuitBreaker(
        name="test_async",
        failure_threshold=1,
        recovery_timeout=0,
        expected_exception=ValueError,
    )

    async def boom() -> int:
        raise ValueError("boom")

    async def ok() -> int:
        return 42

    with pytest.raises(ValueError):
        await breaker.call_async(boom)
    assert breaker.state == CircuitState.OPEN

    result = await breaker.call_async(ok)
    assert result == 42
    assert breaker.state == CircuitState.CLOSED


class _FakeSession:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.unit_of_work as uow_module
    from app.core.unit_of_work import AsyncUnitOfWork

    session = _FakeSession()
    monkeypatch.setattr(uow_module, "AsyncSessionLocal", lambda: session)

    with pytest.raises(ValueError):
        async with AsyncUnitOfWork():
            raise ValueError("boom")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_on_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.unit_of_work as uow_module
    from app.core.unit_of_work import AsyncUnitOfWork

    session = _FakeSession(fail_commit=True)
    monkeypatch.setattr(uow_module, "AsyncSessionLocal", lambda: session)

    with pytest.raises(RuntimeError):
        async with AsyncUnitOfWork():
            pass

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_rate_limit_blocks_excessive_login_attempts(public_async_client) -> None:
    for _ in range(5):
        resp = await public_async_client.post(
            "/api/v1/auth/login",
            data={"username": "someone@example.com", "password": "wrong-password"},
        )
        # First 5 login attempts return 401 (wrong password)
        # Lockout is set after the 5th failed attempt via record_failed_login
        assert resp.status_code == 401

    # 6th attempt triggers the lockout set by the 5th failure
    response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "someone@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 429
    assert "locked" in response.json()["detail"].lower()
    assert response.headers.get("Retry-After")
