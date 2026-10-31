"""Tests for Drivvo domain models."""

import pytest

from custom_components.drivvo.models import (
    Refuelling,
    Service,
    VehicleData,
)


def test_refuelling_from_api_handles_null_volume_and_price():
    api_row = {
        "data": "2025-05-01 10:00:00",
        "odometro": 12345,
        "volume": None,
        "preco": None,
        "valor_total": 200.0,
        "combustivel": "Gasolina",
        "tipo_motivo": 1,
        "tanque_cheio": True,
        "posto_combustivel": {"nome": "Shell"},
    }

    r = Refuelling.from_api(api_row)

    assert r.odometer == 12345
    assert r.total_value == pytest.approx(200.0)
    assert r.volume == pytest.approx(0)  # null volume + null price => 0, not crash


def test_vehicle_data_identification_prefers_name():
    v = VehicleData(
        id=1,
        name="My Car",
        placa="ABC1234",
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[],
        services=[],
        expenses=[],
    )
    assert v.identification == "My Car"


def test_vehicle_data_identification_falls_back_to_placa_then_marca_modelo():
    v = VehicleData(
        id=2,
        name=None,
        placa="XYZ9999",
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[],
        services=[],
        expenses=[],
    )
    assert v.identification == "XYZ9999"

    v2 = VehicleData(
        id=3,
        name=None,
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[],
        services=[],
        expenses=[],
    )
    assert v2.identification == "VW/Gol"


def test_refuelling_from_api_handles_zero_price():
    """Zero price must not crash with ZeroDivisionError; volume falls back to 0."""
    r = Refuelling.from_api(
        {
            "data": "2025-05-01 10:00:00",
            "odometro": 100,
            "volume": None,
            "preco": 0,
            "valor_total": 200.0,
            "combustivel": "Gasolina",
            "tipo_motivo": 1,
            "tanque_cheio": True,
            "posto_combustivel": None,
        }
    )
    assert r.volume == pytest.approx(0.0)


def test_refuelling_from_api_computes_volume_from_price_when_volume_missing():
    """When the API omits volume but provides price + total, derive volume = total/price."""
    r = Refuelling.from_api(
        {
            "data": "2025-05-01 10:00:00",
            "odometro": 100,
            "volume": None,
            "preco": 50.0,
            "valor_total": 200.0,
            "combustivel": "Gasolina",
            "tipo_motivo": 1,
            "tanque_cheio": True,
            "posto_combustivel": None,
        }
    )
    assert r.volume == pytest.approx(4.0)


def _refuelling(date, odo, vol, price, full=True):
    return Refuelling(
        date=date,
        odometer=odo,
        volume=vol,
        price=price,
        total_value=vol * price,
        fuel_type="Gasolina",
        reason=1,
        tank_full=full,
        station="Shell",
    )


def test_vehicle_data_totals_and_averages():
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[
            _refuelling("2025-05-10 12:00:00", 12500, 30.0, 6.0, True),
            _refuelling("2025-05-01 12:00:00", 12200, 28.0, 5.8, True),
            _refuelling("2025-04-20 12:00:00", 12000, 25.0, 5.5, True),
        ],
    )
    assert v.refuelling_total == 3
    assert v.refuelling_value_total == pytest.approx(30 * 6 + 28 * 5.8 + 25 * 5.5)
    assert v.refuelling_volume_total == pytest.approx(83.0)
    assert v.refuelling_price_lowest == pytest.approx(5.5)
    # General average spans the closed full-tank segments only:
    #   12000 -> 12200 covered by the 28 L put in at 12200
    #   12200 -> 12500 covered by the 30 L put in at 12500
    # The 25 L of the opening fill were burnt before the measurement started,
    # over an unknown distance, so Drivvo excludes them: 500 / 58, not 500 / 83.
    assert v.refuelling_general_average == pytest.approx(500 / 58)
    # last_average across two consecutive full tanks: (12500 - 12200) / 30
    assert v.refuelling_last_average == pytest.approx(300 / 30)
    assert v.refuelling_distance == 300


def test_refuelling_last_average_includes_partial_fill_between_full_tanks():
    """Partial fill between two full tanks contributes its volume to the cycle.

    The implementation sums volumes from first_idx (inclusive) up to second_idx
    (exclusive), so the first full tank's own volume IS included in the denominator.
    """
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[
            _refuelling("2025-05-20", 12800, 28.0, 6.0, True),
            _refuelling("2025-05-10", 12500, 15.0, 6.0, False),
            _refuelling("2025-05-01", 12200, 30.0, 5.8, True),
        ],
    )
    # cycle = full(12800, 28L) -> partial(12500, 15L) -> full(12200)
    # distance = 12800 - 12200 = 600
    # volume = first_full(28) + partial(15) = 43  [algorithm includes first_full's own volume]
    assert v.refuelling_last_average == pytest.approx(600 / 43.0)


def test_refuelling_last_average_skips_leading_partial():
    """First entry partial; finds next full, then prior full."""
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[
            _refuelling("2025-05-20", 12700, 10.0, 6.0, False),
            _refuelling("2025-05-15", 12600, 30.0, 6.0, True),
            _refuelling("2025-05-01", 12200, 25.0, 5.8, True),
        ],
    )
    # First full at index 1 (12600, 30L), second full at index 2 (12200)
    # distance = 12600 - 12200 = 400
    # volume = first_full(30) = 30  [no partials between the two fulls]
    assert v.refuelling_last_average == pytest.approx(400 / 30.0)


def test_refuelling_last_average_single_full_tank_returns_none():
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[
            _refuelling("2025-05-20", 12700, 10.0, 6.0, False),
            _refuelling("2025-05-15", 12600, 30.0, 6.0, True),
        ],
    )
    assert v.refuelling_last_average is None


def test_refuelling_last_average_no_full_tanks_returns_none():
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[
            _refuelling("2025-05-20", 12700, 10.0, 6.0, False),
            _refuelling("2025-05-15", 12600, 15.0, 6.0, False),
        ],
    )
    assert v.refuelling_last_average is None


def test_vehicle_data_odometer_from_latest_event():
    v = VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[_refuelling("2025-05-10 12:00:00", 12500, 30, 6)],
        services=[
            Service(
                date="2025-05-12 09:00:00",
                odometer=12600,
                total_value=200,
                description="Wash",
            )
        ],
    )
    assert v.odometer == 12600
    assert v.odometer_date == "2025-05-12 09:00:00"
