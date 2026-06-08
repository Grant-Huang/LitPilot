import httpx
import pytest

from app.llm import http_client


@pytest.fixture(autouse=True)
async def _reset_clients():
    await http_client.aclose_all()
    yield
    await http_client.aclose_all()


async def test_get_async_client_reuses_instance_within_loop() -> None:
    first = http_client.get_async_client()
    second = http_client.get_async_client()
    assert first is second
    assert isinstance(first, httpx.AsyncClient)


async def test_client_has_split_timeout_and_keepalive_pool() -> None:
    client = http_client.get_async_client()
    timeout = client.timeout
    assert timeout.connect == pytest.approx(5.0)
    assert timeout.read == pytest.approx(120.0)
    limits = http_client.DEFAULT_LIMITS
    assert limits.keepalive_expiry and limits.keepalive_expiry > 0
    assert limits.max_keepalive_connections and limits.max_keepalive_connections > 0


async def test_aclose_all_resets_client() -> None:
    first = http_client.get_async_client()
    await http_client.aclose_all()
    assert first.is_closed
    second = http_client.get_async_client()
    assert second is not first
    assert not second.is_closed
