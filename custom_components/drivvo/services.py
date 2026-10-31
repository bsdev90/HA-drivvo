"""Home Assistant services that write records back to Drivvo."""

from __future__ import annotations

import logging
import uuid

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import (
    ATTR_DATE,
    ATTR_FUEL_NAME,
    ATTR_FULL_TANK,
    ATTR_NOTE,
    ATTR_ODOMETER,
    ATTR_PLACE,
    ATTR_PRICE,
    ATTR_STATION,
    ATTR_TOTAL_VALUE,
    ATTR_TYPE,
    ATTR_VALUE,
    ATTR_VEHICLE_ID,
    ATTR_VOLUME,
    DOMAIN,
    MODULE_EXPENSE,
    MODULE_INCOME,
    MODULE_READING,
    MODULE_REFUELLING,
    MODULE_SERVICE,
    SERVICE_ADD_EXPENSE,
    SERVICE_ADD_INCOME,
    SERVICE_ADD_READING,
    SERVICE_ADD_REFUELLING,
    SERVICE_ADD_SERVICE,
    SERVICE_REFRESH,
)
from .dates import format_api_datetime

_LOGGER = logging.getLogger(__name__)

BASE_FIELDS = {
    vol.Required(ATTR_VEHICLE_ID): cv.string,
    vol.Optional(ATTR_DATE): cv.datetime,
    vol.Optional(ATTR_NOTE): cv.string,
}

REFUELLING_SCHEMA = vol.Schema(
    {
        **BASE_FIELDS,
        vol.Required(ATTR_ODOMETER): vol.Coerce(float),
        vol.Optional(ATTR_TOTAL_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_PRICE): vol.Coerce(float),
        vol.Optional(ATTR_VOLUME): vol.Coerce(float),
        vol.Optional(ATTR_FULL_TANK, default=True): cv.boolean,
        vol.Optional(ATTR_FUEL_NAME): cv.string,
        vol.Optional(ATTR_STATION): cv.string,
    }
)

READING_SCHEMA = vol.Schema(
    {**BASE_FIELDS, vol.Required(ATTR_ODOMETER): vol.Coerce(float)}
)

EXPENSE_SCHEMA = vol.Schema(
    {
        **BASE_FIELDS,
        vol.Required(ATTR_TYPE): cv.string,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_ODOMETER): vol.Coerce(float),
    }
)

SERVICE_SCHEMA = vol.Schema(
    {
        **BASE_FIELDS,
        vol.Required(ATTR_TYPE): cv.string,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_ODOMETER): vol.Coerce(float),
        vol.Optional(ATTR_PLACE): cv.string,
    }
)

INCOME_SCHEMA = vol.Schema(
    {
        **BASE_FIELDS,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_TYPE): cv.string,
        vol.Optional(ATTR_ODOMETER): vol.Coerce(float),
    }
)

REFRESH_SCHEMA = vol.Schema({vol.Optional(ATTR_VEHICLE_ID): cv.string})


def _resolve_vehicle(hass: HomeAssistant, vehicle_id: str):
    """Return the client and coordinator that own a vehicle."""
    wanted = str(vehicle_id)
    for store in hass.data.get(DOMAIN, {}).values():
        if not isinstance(store, dict):
            continue
        coordinators = store.get("coordinators", {})
        if wanted in coordinators:
            return store["client"], coordinators[wanted]
    raise HomeAssistantError(
        f"Vehicle {vehicle_id} is not configured in the Drivvo integration"
    )


async def _resolve_named_id(
    client: DrivvoApiClient, path: str, id_key: str, name: str
) -> int:
    """Translate a user supplied name into the id Drivvo expects."""
    items = await client.get_lookup(path)
    wanted = name.strip().lower()
    for item in items:
        if (item.get("nome") or "").strip().lower() == wanted:
            return item[id_key]
    available = ", ".join(sorted(i["nome"] for i in items if i.get("nome")))
    raise HomeAssistantError(
        f"'{name}' not found in {path}. Available: {available or 'none'}"
    )


async def _resolve_fuel(client: DrivvoApiClient, name: str | None) -> int | None:
    """Pick the fuel to log, defaulting to the first one registered."""
    fuels = await client.get_lookup("combustivel")
    active = [item for item in fuels if item.get("ativo", True)]
    if name:
        wanted = name.strip().lower()
        for item in active or fuels:
            if (item.get("nome") or "").strip().lower() == wanted:
                return item["id_combustivel"]
        available = ", ".join(sorted(i["nome"] for i in fuels if i.get("nome")))
        raise HomeAssistantError(
            f"Fuel '{name}' not found. Available: {available or 'none'}"
        )
    pool = active or fuels
    return pool[0]["id_combustivel"] if pool else None


def _envelope(call: ServiceCall, vehicle_id: str) -> dict:
    """Fields every Drivvo record carries."""
    return {
        "id": None,
        "id_unico": str(uuid.uuid4()),
        "id_veiculo": int(vehicle_id),
        "data": format_api_datetime(call.data.get(ATTR_DATE)),
        "ids_arquivos": [],
        "id_motorista": None,
        "observacao": call.data.get(ATTR_NOTE) or "",
    }


async def _submit(client: DrivvoApiClient, coordinator, module: str, payload: dict):
    """POST a record and refresh the vehicle it belongs to."""
    try:
        await client.add_record(module, payload)
    except DrivvoAuthError as err:
        raise HomeAssistantError(f"Drivvo authentication failed: {err}") from err
    except DrivvoApiError as err:
        raise HomeAssistantError(f"Drivvo rejected the record: {err}") from err
    await coordinator.async_request_refresh()


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Drivvo services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_REFUELLING):
        return

    async def add_refuelling(call: ServiceCall) -> None:
        """Log a refuelling."""
        vehicle_id = call.data[ATTR_VEHICLE_ID]
        client, coordinator = _resolve_vehicle(hass, vehicle_id)

        total = call.data.get(ATTR_TOTAL_VALUE)
        price = call.data.get(ATTR_PRICE)
        volume = call.data.get(ATTR_VOLUME)

        # Drivvo stores all three; derive the missing one from the other two.
        if total is None and price is not None and volume is not None:
            total = price * volume
        elif volume is None and total is not None and price:
            volume = total / price
        elif price is None and total is not None and volume:
            price = total / volume

        if total is None or price is None:
            raise HomeAssistantError(
                "Provide at least two of total_value, price and volume"
            )

        station = None
        if call.data.get(ATTR_STATION):
            station = await _resolve_named_id(
                client,
                "postoCombustivel",
                "id_posto_combustivel",
                call.data[ATTR_STATION],
            )

        payload = {
            **_envelope(call, vehicle_id),
            "odometro": int(call.data[ATTR_ODOMETER]),
            "id_combustivel": await _resolve_fuel(
                client, call.data.get(ATTR_FUEL_NAME)
            ),
            "preco": price,
            "valor_total": total,
            "volume": volume or 0,
            "sem_custo": False,
            "tanque_cheio": call.data[ATTR_FULL_TANK],
            "bateria_inicial_pct": None,
            "bateria_final_pct": None,
            "duracao_minutos": None,
            "id_combustivel_dois": None,
            "preco_dois": 0,
            "valor_total_dois": 0,
            "volume_dois": 0,
            "sem_custo_dois": False,
            "tanque_cheio_dois": False,
            "id_combustivel_tres": None,
            "preco_tres": 0,
            "valor_total_tres": 0,
            "volume_tres": 0,
            "sem_custo_tres": False,
            "tanque_cheio_tres": False,
            "esqueceu_anterior": False,
            "id_posto_combustivel": station,
            "id_tipo_motivo": None,
            "id_forma_pagamento": None,
        }
        await _submit(client, coordinator, MODULE_REFUELLING, payload)

    async def add_reading(call: ServiceCall) -> None:
        """Log an odometer reading."""
        vehicle_id = call.data[ATTR_VEHICLE_ID]
        client, coordinator = _resolve_vehicle(hass, vehicle_id)
        payload = {
            **_envelope(call, vehicle_id),
            "odometro": int(call.data[ATTR_ODOMETER]),
        }
        await _submit(client, coordinator, MODULE_READING, payload)

    async def add_expense(call: ServiceCall) -> None:
        """Log an expense."""
        vehicle_id = call.data[ATTR_VEHICLE_ID]
        client, coordinator = _resolve_vehicle(hass, vehicle_id)
        type_id = await _resolve_named_id(
            client, "tipoDespesa", "id_tipo_despesa", call.data[ATTR_TYPE]
        )
        payload = {
            **_envelope(call, vehicle_id),
            "odometro": int(call.data.get(ATTR_ODOMETER) or 0),
            "tipos_despesa": [
                {
                    "id_unico": str(uuid.uuid4()),
                    "id_tipo_despesa": type_id,
                    "valor": call.data[ATTR_VALUE],
                }
            ],
            "id_forma_pagamento": None,
        }
        await _submit(client, coordinator, MODULE_EXPENSE, payload)

    async def add_service(call: ServiceCall) -> None:
        """Log a service."""
        vehicle_id = call.data[ATTR_VEHICLE_ID]
        client, coordinator = _resolve_vehicle(hass, vehicle_id)
        type_id = await _resolve_named_id(
            client, "tipoServico", "id_tipo_servico", call.data[ATTR_TYPE]
        )
        place = None
        if call.data.get(ATTR_PLACE):
            place = await _resolve_named_id(
                client, "local", "id_local", call.data[ATTR_PLACE]
            )
        payload = {
            **_envelope(call, vehicle_id),
            "odometro": int(call.data.get(ATTR_ODOMETER) or 0),
            "tipos_servico": [
                {
                    "id_unico": str(uuid.uuid4()),
                    "id_tipo_servico": type_id,
                    "valor": call.data[ATTR_VALUE],
                }
            ],
            "id_local": place,
            "id_forma_pagamento": None,
        }
        await _submit(client, coordinator, MODULE_SERVICE, payload)

    async def add_income(call: ServiceCall) -> None:
        """Log an income."""
        vehicle_id = call.data[ATTR_VEHICLE_ID]
        client, coordinator = _resolve_vehicle(hass, vehicle_id)
        type_id = 0
        if call.data.get(ATTR_TYPE):
            type_id = await _resolve_named_id(
                client, "tipoReceita", "id_tipo_receita", call.data[ATTR_TYPE]
            )
        payload = {
            **_envelope(call, vehicle_id),
            "odometro": int(call.data.get(ATTR_ODOMETER) or 0),
            "valor": call.data[ATTR_VALUE],
            "id_tipo_receita": type_id,
        }
        await _submit(client, coordinator, MODULE_INCOME, payload)

    async def refresh(call: ServiceCall) -> None:
        """Fetch data again without waiting for the scheduled update."""
        vehicle_id = call.data.get(ATTR_VEHICLE_ID)
        if vehicle_id:
            _client, coordinator = _resolve_vehicle(hass, vehicle_id)
            await coordinator.async_request_refresh()
            return
        for store in hass.data.get(DOMAIN, {}).values():
            if not isinstance(store, dict):
                continue
            for coordinator in store.get("coordinators", {}).values():
                await coordinator.async_request_refresh()

    for name, handler, schema in (
        (SERVICE_ADD_REFUELLING, add_refuelling, REFUELLING_SCHEMA),
        (SERVICE_ADD_READING, add_reading, READING_SCHEMA),
        (SERVICE_ADD_EXPENSE, add_expense, EXPENSE_SCHEMA),
        (SERVICE_ADD_SERVICE, add_service, SERVICE_SCHEMA),
        (SERVICE_ADD_INCOME, add_income, INCOME_SCHEMA),
        (SERVICE_REFRESH, refresh, REFRESH_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=schema)


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the Drivvo services."""
    for name in (
        SERVICE_ADD_REFUELLING,
        SERVICE_ADD_READING,
        SERVICE_ADD_EXPENSE,
        SERVICE_ADD_SERVICE,
        SERVICE_ADD_INCOME,
        SERVICE_REFRESH,
    ):
        hass.services.async_remove(DOMAIN, name)
