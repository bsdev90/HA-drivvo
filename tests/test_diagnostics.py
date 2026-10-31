"""Tests for diagnostics."""
import pytest
from unittest.mock import MagicMock

from custom_components.drivvo.diagnostics import async_get_config_entry_diagnostics
from custom_components.drivvo.const import DOMAIN, CONF_EMAIL, CONF_PASSWORD
from custom_components.drivvo.models import VehicleData


@pytest.mark.asyncio
async def test_diagnostics_redacts_secrets(hass):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        "vehicles": ["100"],
    }

    coord = MagicMock()
    coord.data = VehicleData(
        id=100,
        name="My Car",
        placa="ABC1234",
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
    )
    # Production __init__.py keys coordinators by str(vehicle_id) — enforce here.
    hass.data[DOMAIN] = {"e1": {"client": None, "coordinators": {"100": coord}}}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"][CONF_EMAIL] == "**REDACTED**"
    assert result["entry_data"][CONF_PASSWORD] == "**REDACTED**"
    assert result["vehicles"]["100"]["name"] == "My Car"
    assert result["vehicles"]["100"]["odometer"] is None
