"""Timestamp handling and reminder predictions."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientSession
from homeassistant.util import dt as dt_util

from custom_components.drivvo.api import DrivvoApiClient
from custom_components.drivvo.coordinator import DrivvoDataUpdateCoordinator
from custom_components.drivvo.dates import format_api_datetime, parse_api_datetime
from custom_components.drivvo.models import Service, VehicleData


def test_api_dates_are_local_not_utc(hass):
    """`data` is the account's local time; `data_acao` is its UTC counterpart.

    Labelling `data` as UTC shifted every date sensor by the account offset.
    """
    parsed = parse_api_datetime("2023-08-13 20:20:14")

    assert parsed.tzinfo is not None
    # The wall clock is preserved; only the zone is attached.
    assert (parsed.year, parsed.month, parsed.day) == (2023, 8, 13)
    assert (parsed.hour, parsed.minute, parsed.second) == (20, 20, 14)
    assert parsed.tzinfo == dt_util.DEFAULT_TIME_ZONE


def test_parse_accepts_date_only_and_rejects_garbage(hass):
    assert parse_api_datetime("2026-08-29").hour == 0
    assert parse_api_datetime("not a date") is None
    assert parse_api_datetime(None) is None
    assert parse_api_datetime("") is None


def test_format_round_trips_through_the_local_zone(hass):
    moment = parse_api_datetime("2024-03-01 08:30:00")
    assert format_api_datetime(moment) == "2024-03-01 08:30:00"


def _service(date, odometer, type_id):
    return Service.from_api(
        {
            "data": date,
            "odometro": odometer,
            "tipos_servico": [
                {"id_tipo_servico": type_id, "valor": 100, "nome": "Oil change"}
            ],
        }
    )


@pytest.mark.asyncio
async def test_coordinator_predicts_reminder_due_points(hass):
    """Drivvo stores the rule, not the due date — the coordinator derives it."""
    vehicle = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        services=[_service("2025-01-10 08:00:00", 70200, 99302742)],
        readings=[],
        reminders_raw=[
            {
                "id_lembrete": 7,
                "id_tipo_servico": 99302742,
                "tipo_servico": "Oil change",
                "unico_repetir": 0,
                "repetir_distancia": 10000,
            }
        ],
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "tok"
        client.get_vehicle = AsyncMock(return_value=vehicle)
        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.reminders_total == 1
    reminder = data.next_reminder
    assert reminder["description"] == "Oil change"
    assert reminder["odometer"] == 80200  # 70200 + 10000
    # The service itself is the only odometer known, so nothing is due yet.
    assert reminder["distance_left"] == 10000
    assert reminder["overdue"] is False
    assert data.reminders_overdue == 0


@pytest.mark.asyncio
async def test_coordinator_flags_an_overdue_reminder(hass):
    vehicle = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        services=[
            _service("2025-01-10 08:00:00", 70200, 99302742),
            _service("2025-06-10 08:00:00", 77000, 111),
        ],
        reminders_raw=[
            {
                "id_lembrete": 7,
                "id_tipo_servico": 99302742,
                "tipo_servico": "Oil change",
                "unico_repetir": 0,
                "repetir_distancia": 5000,
            }
        ],
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "tok"
        client.get_vehicle = AsyncMock(return_value=vehicle)
        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    reminder = data.next_reminder
    assert reminder["odometer"] == 75200  # 70200 + 5000
    assert reminder["distance_left"] == 75200 - 77000
    assert reminder["overdue"] is True
    assert data.reminders_overdue == 1


@pytest.mark.asyncio
async def test_vehicle_without_reminders_is_not_overdue(hass):
    vehicle = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "tok"
        client.get_vehicle = AsyncMock(return_value=vehicle)
        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.reminders == []
    assert data.next_reminder is None
    assert data.reminders_overdue == 0
