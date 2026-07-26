"""Reproduces a real reported bug: a single transient hiccup calling n8n's
Calendar Bridge webhook (cold start, a dropped connection, a slow Google
Calendar API response) threw select_doctor's whole slot computation,
forcing the customer to re-tap and redo part of the booking flow — which
is what produced what looked like a duplicate "Choose a Vet" catalogue
send. _call_bridge must retry transient failures instead of giving up
after one attempt."""

import httpx
import pytest

from app.config import Settings
from app.integrations import google_calendar


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json):
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok_response(body):
    request = httpx.Request("POST", "https://example.com/bridge")
    return httpx.Response(200, json=body, request=request)


def _server_error_response():
    request = httpx.Request("POST", "https://example.com/bridge")
    return httpx.Response(500, json={"success": False}, request=request)


def _client_error_response():
    request = httpx.Request("POST", "https://example.com/bridge")
    return httpx.Response(401, json={"success": False, "error": "invalid_secret"}, request=request)


def _settings() -> Settings:
    return Settings(calendar_bridge_url="https://example.com/bridge", calendar_bridge_secret="s")


async def _no_sleep(*args):
    return None


@pytest.mark.asyncio
async def test_retries_transport_error_then_succeeds(monkeypatch):
    fake = _FakeAsyncClient([httpx.ConnectError("boom"), _ok_response({"success": True, "busy": []})])
    monkeypatch.setattr(google_calendar.httpx, "AsyncClient", lambda **kwargs: fake)
    monkeypatch.setattr(google_calendar.asyncio, "sleep", _no_sleep)

    result = await google_calendar._call_bridge(_settings(), "list_busy", time_min="a", time_max="b")

    assert result["success"] is True
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_retries_5xx_then_succeeds(monkeypatch):
    fake = _FakeAsyncClient([_server_error_response(), _ok_response({"success": True, "busy": []})])
    monkeypatch.setattr(google_calendar.httpx, "AsyncClient", lambda **kwargs: fake)
    monkeypatch.setattr(google_calendar.asyncio, "sleep", _no_sleep)

    result = await google_calendar._call_bridge(_settings(), "list_busy", time_min="a", time_max="b")

    assert result["success"] is True
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_does_not_retry_4xx():
    fake = _FakeAsyncClient([_client_error_response()])

    import unittest.mock
    with unittest.mock.patch.object(google_calendar.httpx, "AsyncClient", lambda **kwargs: fake):
        with pytest.raises(httpx.HTTPStatusError):
            await google_calendar._call_bridge(_settings(), "list_busy", time_min="a", time_max="b")

    assert fake.calls == 1


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(monkeypatch):
    fake = _FakeAsyncClient([httpx.ConnectError("1"), httpx.ConnectError("2"), httpx.ConnectError("3")])
    monkeypatch.setattr(google_calendar.httpx, "AsyncClient", lambda **kwargs: fake)
    monkeypatch.setattr(google_calendar.asyncio, "sleep", _no_sleep)

    with pytest.raises(httpx.ConnectError):
        await google_calendar._call_bridge(_settings(), "list_busy", time_min="a", time_max="b")

    assert fake.calls == google_calendar.BRIDGE_MAX_ATTEMPTS
