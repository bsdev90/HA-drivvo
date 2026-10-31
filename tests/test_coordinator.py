"""Tests for DrivvoDataUpdateCoordinator."""
import pytest
from aiohttp import ClientSession
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.drivvo.coordinator import DrivvoDataUpdateCoordinator
from custom_components.drivvo.api import DrivvoApiClient, DrivvoAuthError
from custom_components.drivvo.models import VehicleData


@pytest.mark.asyncio
async def test_coordinator_logs_in_then_fetches_vehicle(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.login = AsyncMock(return_value="tok")
        client.get_vehicle = AsyncMock(
            return_value=VehicleData(
                id=1,
                name="X",
                placa=None,
                manufacturer="VW",
                model="Gol",
                distance_unit="km",
                currency="R$",
            )
        )

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.id == 1
    client.login.assert_awaited_once()
    client.get_vehicle.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_coordinator_reuses_token_on_subsequent_refresh(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "existing"
        client.login = AsyncMock(return_value="existing")
        client.get_vehicle = AsyncMock(
            return_value=VehicleData(
                id=1,
                name="X",
                placa=None,
                manufacturer="VW",
                model="Gol",
                distance_unit="km",
                currency="R$",
            )
        )

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        await coord._async_update_data()

    client.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_retries_login_on_auth_error(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "stale"
        calls = []

        async def fake_get_vehicle(_):
            if not calls:
                calls.append(1)
                raise DrivvoAuthError("expired")
            return VehicleData(
                id=1,
                name="X",
                placa=None,
                manufacturer="VW",
                model="Gol",
                distance_unit="km",
                currency="R$",
            )

        client.get_vehicle = fake_get_vehicle
        client.login = AsyncMock(return_value="fresh")

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.id == 1
    client.login.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_wraps_api_error_in_update_failed(hass):
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from custom_components.drivvo.api import DrivvoApiError

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "tok"
        client.login = AsyncMock()
        client.get_vehicle = AsyncMock(side_effect=DrivvoApiError("boom"))

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        with pytest.raises(UpdateFailed, match="boom"):
            await coord._async_update_data()

    client.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_raises_config_entry_auth_failed_on_persistent_auth_error(
    hass
):
    """Second login attempt rejected (e.g. user changed password) → ConfigEntryAuthFailed."""
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "stale"
        client.get_vehicle = AsyncMock(side_effect=DrivvoAuthError("expired"))
        client.login = AsyncMock(side_effect=DrivvoAuthError("rejected"))

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_config_entry_auth_failed_on_cold_login_failure(hass):
    """No cached token, first login rejected → ConfigEntryAuthFailed."""
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = None
        client.login = AsyncMock(side_effect=DrivvoAuthError("rejected"))
        client.get_vehicle = AsyncMock()

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    client.get_vehicle.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_retry_get_vehicle_api_error_wraps_in_update_failed(hass):
    """After successful re-login, second get_vehicle raises non-auth error → UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from custom_components.drivvo.api import DrivvoApiError

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "stale"
        calls = []

        async def fake_get_vehicle(_):
            if not calls:
                calls.append(1)
                raise DrivvoAuthError("expired")
            raise DrivvoApiError("500")

        client.get_vehicle = fake_get_vehicle
        client.login = AsyncMock(return_value="fresh")

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        with pytest.raises(UpdateFailed, match="500"):
            await coord._async_update_data()
