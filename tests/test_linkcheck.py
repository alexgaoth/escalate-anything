import httpx
import pytest

from redress import linkcheck
from redress.linkcheck import collect_urls


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_collect_urls_includes_sources_and_url_channels(fixture_registry):
    urls = collect_urls(fixture_registry)
    assert "https://www.example.com/baggage/claim" in urls  # web_form value
    assert "https://www.example.com/contact" in urls  # source
    assert not any(u.startswith("+1") for u in urls)  # phone values are not URLs


@pytest.mark.anyio
async def test_head_404_is_retried_with_get():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if request.method == "HEAD" else 200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        import asyncio
        r = await linkcheck._check(client, asyncio.Semaphore(1), "https://x.example/", ["a"])
    assert r.status == "ok"


@pytest.mark.anyio
async def test_tls_errors_are_not_dead():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        import asyncio
        r = await linkcheck._check(client, asyncio.Semaphore(1), "https://x.example/", ["a"])
    assert r.status == "error"


@pytest.mark.anyio
async def test_known_bot_404_hosts_are_blocked_not_dead():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        import asyncio
        r = await linkcheck._check(client, asyncio.Semaphore(1), "https://www.ftc.gov/contact", ["a"])
    assert r.status == "blocked"
