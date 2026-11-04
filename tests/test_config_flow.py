"""Tests for Drivvo config flow."""

import pytest

from homeassistant import config_entries, data_entry_flow

from custom_components.drivvo.const import DOMAIN
from tests.conftest import load


@pytest.mark.asyncio
async def test_user_flow_success(hass, enable_custom_integrations, mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/web",
        payload=load("vehicle_list.json"),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": "user@example.com", "password": "secret"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "vehicle"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"vehicles": ["100"]},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["email"] == "user@example.com"
    assert result["data"]["vehicles"] == ["100"]


@pytest.mark.asyncio
async def test_user_flow_invalid_auth(
    hass, enable_custom_integrations, mock_aioresponse
):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        status=401,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": "user@example.com", "password": "wrong"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"password": "auth_error"}


@pytest.mark.parametrize("source", ["user", "reauth", "options"])
@pytest.mark.parametrize("failure", ["connection", "server", "auth"])
async def test_flow_login_errors(hass, enable_custom_integrations, source, failure):
    from unittest.mock import AsyncMock, patch
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.drivvo.api import (
        DrivvoApiClient,
        DrivvoApiError,
        DrivvoAuthError,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            "email": "user@example.com",
            "password": "secret",
            "vehicles": ["100"],
        },
    )
    if source != "user":
        entry.add_to_hass(hass)
    error = (
        DrivvoAuthError("rejected") if failure == "auth" else DrivvoApiError("offline")
    )
    with patch.object(DrivvoApiClient, "login", AsyncMock(side_effect=error)):
        if source == "options":
            result = await hass.config_entries.options.async_init(entry.entry_id)
            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "init"
        else:
            context = {"source": source}
            if source == "reauth":
                context["entry_id"] = entry.entry_id
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context=context,
                data=entry.data if source == "reauth" else None,
            )
        manager = (
            hass.config_entries.options
            if source == "options"
            else hass.config_entries.flow
        )
        submitted = {"email": "user@example.com", "password": "secret"}
        if source == "options":
            submitted["vehicles"] = ["100"]
        result = await manager.async_configure(result["flow_id"], submitted)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == (
        {"password": "auth_error"} if failure == "auth" else {"base": "cannot_connect"}
    )
    assert entry.data["vehicles"] == ["100"]


async def test_options_opens_with_framework_config_entry(
    hass, enable_custom_integrations
):
    from unittest.mock import AsyncMock, patch
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.drivvo.api import DrivvoApiClient

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            "email": "user@example.com",
            "password": "secret",
            "vehicles": ["100"],
        },
    )
    entry.add_to_hass(hass)
    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(
            DrivvoApiClient,
            "get_vehicles",
            AsyncMock(return_value=load("vehicle_list.json")),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {}
