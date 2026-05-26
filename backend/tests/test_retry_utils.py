import pytest

from app.agents.retry_utils import retry_async


@pytest.mark.asyncio
async def test_retry_async_succeeds_second_try() -> None:
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("fail")
        return "ok"

    result = await retry_async(fn, max_retries=2, delay_ms=0)
    assert result == "ok"
    assert calls == 2
