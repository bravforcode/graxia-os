"""Integration test fixtures — Docker containers for Postgres + Redis."""
import pytest

pytest.importorskip("testcontainers")

from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:15-alpine") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis.get_connection_url()
