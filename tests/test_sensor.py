"""Tests for Drivvo sensor descriptions."""
import pytest
from types import SimpleNamespace
from custom_components.drivvo.models import VehicleData, Service, Expense
from custom_components.drivvo.sensors import SENSOR_TYPES
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


def _vehicle_with_services_and_expenses() -> VehicleData:
    return VehicleData(
        id=1,
        name="X",
        placa=None,
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        services=[
            Service(
                date="2025-05-12 09:00:00",
                odometer=12600,
                total_value=200.0,
                description="Oil change",
            ),
            Service(
                date="2025-04-12 09:00:00",
                odometer=12100,
                total_value=150.0,
                description="Tire rotation",
            ),
        ],
        expenses=[
            Expense(
                date="2025-05-10 09:00:00",
                odometer=12500,
                total_value=80.0,
                description="Toll",
                expense_type="Pedágio",
            ),
        ],
    )


def _find(key):
    for s in SENSOR_TYPES:
        if s.key == key:
            return s
    raise KeyError(key)


@pytest.mark.parametrize(
    "unit,expected",
    [("L", SensorDeviceClass.VOLUME_STORAGE),
     ("gal", SensorDeviceClass.VOLUME_STORAGE),
     ("kWh", SensorDeviceClass.ENERGY_STORAGE),
     ("gal UK", None)],
)
def test_remaining_fuel_is_stored_quantity(unit, expected):
    vehicle = SimpleNamespace(volume_unit=unit)
    remaining = _find("fuel_remaining")
    assert remaining.device_class_fn(vehicle) == expected
    assert remaining.state_class == SensorStateClass.MEASUREMENT
    # Refuellings remain accumulated volumes, not stored quantities.
    if unit in ("L", "gal"):
        assert _find("refuelling_volume").device_class_fn(vehicle) == SensorDeviceClass.VOLUME


def test_service_total_and_last_sensors():
    v = _vehicle_with_services_and_expenses()
    assert _find("service_total").value_fn(v) == 2
    assert _find("service_value_total").value_fn(v) == pytest.approx(350.0)
    assert _find("service_date").value_fn(v) == "2025-05-12 09:00:00"
    assert _find("service_odometer").value_fn(v) == 12600
    assert _find("service_value").value_fn(v) == pytest.approx(200.0)
    assert _find("service_description").value_fn(v) == "Oil change"


def test_expense_total_and_last_sensors():
    v = _vehicle_with_services_and_expenses()
    assert _find("expense_total").value_fn(v) == 1
    assert _find("expense_value_total").value_fn(v) == pytest.approx(80.0)
    assert _find("expense_date").value_fn(v) == "2025-05-10 09:00:00"
    assert _find("expense_value").value_fn(v) == pytest.approx(80.0)
    assert _find("expense_type").value_fn(v) == "Pedágio"
