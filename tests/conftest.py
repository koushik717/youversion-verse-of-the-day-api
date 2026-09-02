import httpx
import pytest
from fastapi.testclient import TestClient

from app.client import YouVersionClient
from app.main import app


@pytest.fixture
def make_client():
    """
    Factory fixture: pass an httpx.MockTransport-style handler
    `(httpx.Request) -> httpx.Response`, get back a TestClient wired to a
    YouVersionClient whose HTTP calls are served entirely by that handler
    (no network access, no lifespan startup involved).
    """

    def _make(handler):
        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(
            transport=transport, base_url="https://api.youversion.com"
        )
        app.state.youversion = YouVersionClient(http_client=mock_http_client)
        return TestClient(app)

    return _make
