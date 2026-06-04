import pytest


def test_smoke():
    assert True


@pytest.mark.asyncio
async def test_async_smoke():
    assert True
