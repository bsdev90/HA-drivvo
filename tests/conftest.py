"""Shared test fixtures."""
import json
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from aioresponses import aioresponses
import aioresponses.core as mock_http_core
from aiohttp import ClientResponse


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def compatible_mock_response(monkeypatch):
    """Supply aiohttp's new stream writer argument in mocked responses only."""
    if "stream_writer" not in inspect.signature(ClientResponse).parameters:
        return

    class MockClientResponse(ClientResponse):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(mock_http_core, "ClientResponse", MockClientResponse)


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m


# In asyncio_mode=strict, the phcc `enable_custom_integrations` fixture is sync
# but depends on the async `hass` fixture, so pytest-asyncio 0.23 passes the
# generator object instead of the resolved HomeAssistant instance.  We override
# it here with an async fixture that does the same pop correctly.
@pytest.fixture
async def enable_custom_integrations(hass):
    """Async-safe override of phcc's enable_custom_integrations fixture."""
    hass.data.pop("custom_components", None)
    yield
