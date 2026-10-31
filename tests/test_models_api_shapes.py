"""The shapes the Drivvo web API actually returns.

The service and expense endpoints do not return ``valor_total`` — the amount is
split per type in ``tipos_servico`` / ``tipos_despesa``. These tests pin that
shape, which was verified against live responses from api.drivvo.com.
"""

import pytest

from custom_components.drivvo.models import (
    AccountConfig,
    Checklist,
    Expense,
    Income,
    Reading,
    Refuelling,
    Route,
    Service,
    VehicleData,
)

from .conftest import load


def _vehicle(**kwargs) -> VehicleData:
    base = {
        "id": 100,
        "name": "X",
        "placa": None,
        "manufacturer": "VW",
        "model": "Gol",
        "distance_unit": "km",
        "currency": "R$",
    }
    base.update(kwargs)
    return VehicleData(**base)


def test_service_reads_typed_lines_not_valor_total():
    rows = load("services_real_shape.json")

    service = Service.from_api(rows[0])

    assert service.total_value == pytest.approx(168.0)  # 137 + 31
    assert service.description == "Oil change, Lights"
    assert service.place == "Ari Auto Parts"
    assert service.type_ids == (99302742, 99302762)


def test_expense_reads_typed_lines_not_valor_total():
    rows = load("expenses_real_shape.json")

    expense = Expense.from_api(rows[0])

    assert expense.total_value == pytest.approx(850.5)
    assert expense.description == "IPVA"
    assert expense.type_ids == (5501,)


def test_typed_lines_fall_back_to_valor_total():
    """Older/other shapes that carry a flat total still parse."""
    service = Service.from_api(
        {
            "data": "2025-01-01 00:00:00",
            "odometro": 10,
            "valor_total": 42.0,
            "descricao": "Flat",
        }
    )
    assert service.total_value == pytest.approx(42.0)
    assert service.description == "Flat"


def test_refuelling_prefers_the_price_derived_volume():
    """Drivvo derives the volume from what was paid, as the app does."""
    refuelling = Refuelling.from_api(
        {"odometro": 100, "volume": None, "preco": 5.79, "valor_total": 100.0}
    )
    assert refuelling.volume == pytest.approx(100 / 5.79)


def test_refuelling_keeps_volume_when_free():
    refuelling = Refuelling.from_api(
        {
            "odometro": 100,
            "volume": 12.0,
            "preco": 0,
            "valor_total": 0,
            "sem_custo": True,
        }
    )
    assert refuelling.volume == pytest.approx(12.0)


def test_electric_fields_are_parsed():
    refuelling = Refuelling.from_api(
        {
            "odometro": 100,
            "volume": 20,
            "preco": 1,
            "valor_total": 20,
            "id_tipo_combustivel": 4,
            "bateria_inicial_pct": 20,
            "bateria_final_pct": 80,
            "duracao_minutos": 45,
        }
    )
    assert refuelling.battery_start == 20
    assert refuelling.battery_end == 80
    assert refuelling.duration == 45


def test_charge_energy_from_battery_delta_and_pack_size():
    vehicle = _vehicle(
        fuel_type_id=4,
        tank_volume=60.0,
        refuellings=[
            Refuelling.from_api(
                {
                    "data": "2025-01-01 00:00:00",
                    "odometro": 100,
                    "volume": 36,
                    "preco": 1,
                    "valor_total": 36,
                    "bateria_inicial_pct": 20,
                    "bateria_final_pct": 80,
                }
            )
        ],
    )
    assert vehicle.charge_energy == pytest.approx(36.0)  # (80-20)% of 60 kWh
    assert vehicle.volume_unit == "kWh"


def test_units_follow_the_account_configuration():
    config = AccountConfig.from_api(
        {
            "formato_valor": "USD",
            "unidade_distancia": 2,
            "unidade_medida": 2,
            "eficiencia_combustivel": 8,
        }
    )
    vehicle = _vehicle(distance_unit="mi", distance_unit_id=2, config=config)

    assert vehicle.volume_unit == "gal"
    assert vehicle.efficiency_unit == "mpg"


def test_hour_based_vehicles_report_volume_per_hour():
    config = AccountConfig.from_api({"unidade_distancia": 3})
    vehicle = _vehicle(distance_unit="h", distance_unit_id=3, config=config)

    assert vehicle.efficiency_unit == "L/h"


def _full(date, odometer, volume):
    return Refuelling.from_api(
        {
            "data": date,
            "odometro": odometer,
            "volume": volume,
            "preco": 1,
            "valor_total": volume,
            "sem_custo": True,
            "tanque_cheio": True,
        }
    )


def test_fuel_level_estimated_from_distance_since_last_full_tank():
    vehicle = _vehicle(
        tank_volume=50.0,
        refuellings=[
            _full("2025-02-01 00:00:00", 1400, 40.0),
            _full("2025-01-01 00:00:00", 1000, 30.0),
        ],
        readings=[Reading.from_api({"data": "2025-02-11 00:00:00", "odometro": 1500})],
    )
    # 400 km on 40 L => 0.1 L/km; 100 km since the last full tank => 10 L used.
    assert vehicle.fuel_remaining == pytest.approx(40.0)
    assert vehicle.fuel_level == pytest.approx(80.0)
    assert vehicle.fuel_range == pytest.approx(400.0)


def test_fuel_level_is_unknown_without_a_tank_volume():
    vehicle = _vehicle(
        refuellings=[
            _full("2025-02-01 00:00:00", 1400, 40.0),
            _full("2025-01-01 00:00:00", 1000, 30.0),
        ]
    )
    assert vehicle.fuel_level is None


def test_odometer_considers_every_module():
    vehicle = _vehicle(
        refuellings=[_full("2025-01-01 00:00:00", 1000, 30.0)],
        readings=[Reading.from_api({"data": "2025-03-01 00:00:00", "odometro": 1800})],
        checklists=[
            Checklist.from_api({"data": "2025-02-01 00:00:00", "odometro": 1500})
        ],
        routes=[
            Route.from_api(
                {
                    "data": "2025-01-15 00:00:00",
                    "odometro_inicial": 1100,
                    "odometro_final": 1200,
                }
            )
        ],
    )
    assert vehicle.odometer == 1800
    assert vehicle.odometer_date == "2025-03-01 00:00:00"
    assert vehicle.route_distance_total == 100


def test_cost_total_sums_the_three_spending_modules():
    vehicle = _vehicle(
        refuellings=[_full("2025-01-01 00:00:00", 1000, 30.0)],
        services=[Service.from_api(load("services_real_shape.json")[0])],
        expenses=[Expense.from_api(load("expenses_real_shape.json")[0])],
        incomes=[Income.from_api({"data": "2025-01-02 00:00:00", "valor": 200})],
    )
    assert vehicle.cost_total == pytest.approx(30.0 + 168.0 + 850.5)
    assert vehicle.income_value_total == pytest.approx(200.0)
