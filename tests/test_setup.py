"""End-to-end setup of the config entry.

Every module imports and every model parses on its own, and the integration
still failed to finish `async_setup_entry` on a real instance. This exercises
the whole path so that cannot happen unnoticed again.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.drivvo.api import DrivvoApiClient
from custom_components.drivvo.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VEHICLES,
    DOMAIN,
)

VEHICLE_ID = "100"

PAYLOADS = {
    "/veiculo/web": [{"id_veiculo": 100}],
    f"/veiculo/{VEHICLE_ID}": {
        "id_veiculo": 100,
        "nome": "My Car",
        "placa": "ABC1234",
        "marca": "VW",
        "modelo": "Gol",
        "unidade_distancia": 1,
        "id_tipo_combustivel": 1,
        "volume_tanque": 50,
    },
    f"/veiculo/{VEHICLE_ID}/abastecimento/web": [
        {
            "data": "2025-05-10 12:00:00",
            "odometro": 12500,
            "volume": None,
            "preco": 6.0,
            "valor_total": 180.0,
            "combustivel": "Gasolina",
            "tanque_cheio": True,
        },
        {
            "data": "2025-04-20 12:00:00",
            "odometro": 12000,
            "volume": None,
            "preco": 5.5,
            "valor_total": 137.5,
            "combustivel": "Gasolina",
            "tanque_cheio": True,
        },
    ],
    f"/veiculo/{VEHICLE_ID}/servico/web": [
        {
            "data": "2025-03-01 09:00:00",
            "odometro": 11800,
            "tipos_servico": [
                {"id_tipo_servico": 7, "valor": 168.0, "nome": "Oil change"}
            ],
        }
    ],
    f"/veiculo/{VEHICLE_ID}/despesa/web": [],
    "/configuracao": [{"formato_valor": "R$", "unidade_distancia": 1}],
    f"/veiculo/{VEHICLE_ID}/receita/web": [],
    f"/veiculo/{VEHICLE_ID}/percurso/web": [],
    f"/veiculo/{VEHICLE_ID}/leitura/web": [],
    f"/veiculo/{VEHICLE_ID}/lembrete/web": [
        {
            "id_lembrete": 3,
            "id_tipo_servico": 7,
            "tipo_servico": "Oil change",
            "unico_repetir": 0,
            "repetir_distancia": 10000,
        }
    ],
    f"/veiculo/{VEHICLE_ID}/checklist/web": [],
    "/usuario": {"cnh_validade": "2030-01-01"},
}


async def _fake_get(self, path):
    return PAYLOADS[path]


@pytest.fixture
def entry(hass):
    item = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_VEHICLES: [VEHICLE_ID],
        },
    )
    item.add_to_hass(hass)
    return item


@pytest.mark.asyncio
async def test_setup_entry_loads_and_creates_entities(
    hass, entry, enable_custom_integrations
):
    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "_get_json", _fake_get),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    odometer = hass.states.get("sensor.my_car_odometer_value")
    assert odometer is not None
    assert odometer.state == "12500"

    # The full-tank segment is 12000 -> 12500 on the 30 L put in at 12500.
    average = hass.states.get("sensor.my_car_refuelling_general_average")
    assert average is not None
    assert float(average.state) == pytest.approx(500 / 30, rel=1e-3)

    # Services and expenses carry their amount in typed lines, not valor_total.
    service_value = hass.states.get("sensor.my_car_service_value")
    assert service_value is not None
    assert float(service_value.state) == pytest.approx(168.0)


@pytest.mark.asyncio
async def test_setup_registers_the_write_back_services(
    hass, entry, enable_custom_integrations
):
    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "_get_json", _fake_get),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for name in (
        "add_refuelling",
        "add_reading",
        "add_expense",
        "add_service",
        "add_income",
        "refresh",
    ):
        assert hass.services.has_service(DOMAIN, name), name


@pytest.mark.asyncio
async def test_setup_creates_the_maintenance_binary_sensor(
    hass, entry, enable_custom_integrations
):
    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "_get_json", _fake_get),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    due = hass.states.get("binary_sensor.my_car_maintenance_due")
    assert due is not None
    # Reminder is due at 11800 + 10000; the vehicle is at 12500, so not overdue.
    assert due.state == "off"
    assert len(due.attributes["reminders"]) == 1


@pytest.mark.asyncio
async def test_unload_removes_the_services(hass, entry, enable_custom_integrations):
    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "_get_json", _fake_get),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "add_refuelling")


@pytest.mark.parametrize("phase", ["login", "list", "refresh"])
async def test_temporary_failure_retries_without_missing_vehicle_repair(
    hass, entry, enable_custom_integrations, phase, freezer
):
    from custom_components.drivvo.api import DrivvoApiError
    from homeassistant.helpers import issue_registry as ir

    async def get_json(self, path):
        if phase == "list" and path == "/veiculo/web":
            raise DrivvoApiError("offline")
        if phase == "refresh" and path == f"/veiculo/{VEHICLE_ID}":
            raise DrivvoApiError("offline")
        return PAYLOADS[path]

    with (
        patch.object(
            DrivvoApiClient,
            "login",
            AsyncMock(
                side_effect=DrivvoApiError("offline") if phase == "login" else None,
                return_value="tok",
            ),
        ),
        patch.object(DrivvoApiClient, "_get_json", get_json),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert (DOMAIN, f"{VEHICLE_ID}_vehicle_non_existent") not in ir.async_get(
        hass
    ).issues
    assert entry.entry_id not in hass.data.get(DOMAIN, {})

    # The scheduled Home Assistant retry recovers and restores entities.
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "_get_json", _fake_get),
    ):
        freezer.tick(timedelta(seconds=10))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.my_car_odometer_value") is not None


async def test_confirmed_missing_vehicle_creates_repair(
    hass, entry, enable_custom_integrations
):
    from homeassistant.helpers import issue_registry as ir

    with (
        patch.object(DrivvoApiClient, "login", AsyncMock(return_value="tok")),
        patch.object(DrivvoApiClient, "get_vehicles", AsyncMock(return_value=[])),
        patch.object(DrivvoApiClient, "get_vehicle", AsyncMock()) as get_vehicle,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    get_vehicle.assert_not_called()
    assert (DOMAIN, f"{VEHICLE_ID}_vehicle_non_existent") in ir.async_get(hass).issues
