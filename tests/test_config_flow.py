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
