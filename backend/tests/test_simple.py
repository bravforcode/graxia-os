"""Simple test to check if pytest works at all."""

import pytest


def test_simple_sync():
    """Simplest possible test."""
    assert 1 + 1 == 2


@pytest.mark.asyncio
async def test_simple_async():
    """Simple async test."""
    import asyncio

    await asyncio.sleep(0.001)
    assert True
