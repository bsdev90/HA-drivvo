"""Sensor platform for Drivvo integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime

from .models import VehicleData
from .units import UnitOfDrivvoVolume


@dataclass
class DrivvoSensorEntityDescription(SensorEntityDescription):
    """Class describing Drivvo sensor entities."""

    value_fn: Callable | None = None
    unit_fn: Callable[[VehicleData], str] | None = None
    device_class_fn: Callable[[VehicleData], SensorDeviceClass | None] | None = None
    attributes_fn: Callable[[VehicleData], dict[str, Any]] | None = None


def _distance_device_class(data: VehicleData) -> SensorDeviceClass | None:
    """Vehicles measured in hours report a duration, not a distance."""
    if data.distance_unit in ("km", "mi"):
        return SensorDeviceClass.DISTANCE
    return None


def _volume_device_class(data: VehicleData) -> SensorDeviceClass | None:
    """Map the account volume unit to a device class Home Assistant accepts."""
    if data.volume_unit == UnitOfDrivvoVolume.KILOWATT_HOURS:
        return SensorDeviceClass.ENERGY
    if data.volume_unit in (UnitOfDrivvoVolume.LITERS, UnitOfDrivvoVolume.GALLONS_US):
        return SensorDeviceClass.VOLUME
    # Imperial gallons have no device class in Home Assistant.
    return None


def _vehicle_attributes(data: VehicleData) -> dict[str, Any]:
    """Vehicle details that do not warrant a sensor of their own."""
    return {
        "license_plate": data.placa,
        "year": data.year,
        "chassis": data.chassis,
        "renavam": data.renavam,
        "tank_volume": data.tank_volume,
        "dual_fuel": data.dual_fuel,
        "primary": data.primary,
        "active": data.active,
        "purchase_value": data.purchase_value,
        "sale_value": data.sale_value,
        "note": data.note,
        "distance_unit": data.distance_unit,
        "volume_unit": data.volume_unit,
        "efficiency_unit": data.efficiency_unit,
    }


def reminder_attributes(data: VehicleData) -> dict[str, Any]:
    """Full reminder list, so automations can iterate instead of guessing."""
    return {
        "reminders": [
            {
                "description": item["description"],
                "date": item["date"].isoformat() if item["date"] else None,
                "odometer": item["odometer"],
                "days_left": item["days_left"],
                "distance_left": item["distance_left"],
                "overdue": item["overdue"],
                "note": item["note"],
            }
            for item in data.reminders
        ]
    }


SENSOR_TYPES: tuple[DrivvoSensorEntityDescription, ...] = (
    DrivvoSensorEntityDescription(
        key="refuelling_total",
        translation_key="refuelling_total",
        name="Refuelling Total",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.refuelling_total,
    ),
    DrivvoSensorEntityDescription(
        key="vehicle",
        translation_key="vehicle",
        name="Vehicle",
        icon="mdi:car",
        value_fn=lambda data, model: model,
        attributes_fn=_vehicle_attributes,
    ),
    DrivvoSensorEntityDescription(
        key="odometer",
        translation_key="odometer_value",
        name="Odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.odometer,
    ),
    DrivvoSensorEntityDescription(
        key="odometer_date",
        translation_key="odometer_date",
        name="Odometer Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.odometer_date,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_last_average",
        translation_key="refuelling_last_average",
        name="Refuelling Last Average",
        icon="mdi:fuel",
        state_class=SensorStateClass.MEASUREMENT,
        unit_fn=lambda data: data.efficiency_unit,
        value_fn=lambda data: data.refuelling_last_average,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_general_average",
        translation_key="refuelling_general_average",
        name="Refuelling General Average",
        icon="mdi:fuel",
        state_class=SensorStateClass.MEASUREMENT,
        unit_fn=lambda data: data.efficiency_unit,
        value_fn=lambda data: data.refuelling_general_average,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_station",
        translation_key="refuelling_station",
        name="Refuelling Station",
        icon="mdi:gas-station",
        value_fn=lambda data: (
            data.last_refuelling.station if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_type",
        translation_key="refuelling_type",
        name="Refuelling Type",
        icon="mdi:gas-station",
        value_fn=lambda data: (
            data.last_refuelling.fuel_type if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_reason",
        translation_key="refuelling_reason",
        name="Refuelling Reason",
        icon="mdi:information-outline",
        value_fn=lambda data: (
            data.last_refuelling.reason if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_date",
        translation_key="refuelling_date",
        name="Refuelling Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: (
            data.last_refuelling.date if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_odometer",
        translation_key="refuelling_odometer",
        name="Refuelling Odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: (
            data.last_refuelling.odometer if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_value",
        translation_key="refuelling_value",
        name="Refuelling Value",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: (
            data.last_refuelling.total_value if data.last_refuelling else None
        ),
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_price",
        translation_key="refuelling_price",
        name="Refuelling Price",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: (
            data.last_refuelling.price if data.last_refuelling else None
        ),
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_value_total",
        translation_key="refuelling_value_total",
        name="Refuelling Value Total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: data.refuelling_value_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_tank_full",
        translation_key="refuelling_tank_full",
        name="Refuelling Tank Full",
        icon="mdi:gas-station",
        value_fn=lambda data: (
            data.last_refuelling.tank_full if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_distance",
        translation_key="refuelling_distance",
        name="Refuelling Distance",
        icon="mdi:road",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.refuelling_distance,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_price_lowest",
        translation_key="refuelling_price_lowest",
        name="Refuelling Price Lowest",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: data.refuelling_price_lowest,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_volume",
        translation_key="refuelling_volume",
        name="Refuelling Volume",
        icon="mdi:fuel",
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.TOTAL,
        device_class_fn=_volume_device_class,
        unit_fn=lambda data: data.volume_unit,
        value_fn=lambda data: (
            data.last_refuelling.volume if data.last_refuelling else None
        ),
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_volume_total",
        translation_key="refuelling_volume_total",
        name="Refuelling Volume Total",
        icon="mdi:fuel",
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.TOTAL,
        device_class_fn=_volume_device_class,
        unit_fn=lambda data: data.volume_unit,
        value_fn=lambda data: data.refuelling_volume_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="service_total",
        translation_key="service_total",
        name="Service Total",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.service_total,
    ),
    DrivvoSensorEntityDescription(
        key="service_value_total",
        translation_key="service_value_total",
        name="Service Value Total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.service_value_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="service_date",
        translation_key="service_date",
        name="Service Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_service.date if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="service_odometer",
        translation_key="service_odometer",
        name="Service Odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda d: d.last_service.odometer if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="service_value",
        translation_key="service_value",
        name="Service Value",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.last_service.total_value if d.last_service else None,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="service_description",
        translation_key="service_description",
        name="Service Description",
        icon="mdi:wrench",
        value_fn=lambda d: d.last_service.description if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_total",
        translation_key="expense_total",
        name="Expense Total",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.expense_total,
    ),
    DrivvoSensorEntityDescription(
        key="expense_value_total",
        translation_key="expense_value_total",
        name="Expense Value Total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.expense_value_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="expense_date",
        translation_key="expense_date",
        name="Expense Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_expense.date if d.last_expense else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_value",
        translation_key="expense_value",
        name="Expense Value",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.last_expense.total_value if d.last_expense else None,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="expense_type",
        translation_key="expense_type",
        name="Expense Type",
        icon="mdi:tag",
        value_fn=lambda d: d.last_expense.expense_type if d.last_expense else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_description",
        translation_key="expense_description",
        name="Expense Description",
        icon="mdi:information-outline",
        value_fn=lambda d: d.last_expense.description if d.last_expense else None,
    ),
    # --- Costs -------------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="refuelling_cost_distance",
        translation_key="refuelling_cost_distance",
        name="Fuel Cost per Distance",
        icon="mdi:cash-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        unit_fn=lambda data: f"{data.currency}/{data.distance_unit}",
        value_fn=lambda data: data.refuelling_cost_distance,
        suggested_display_precision=3,
    ),
    DrivvoSensorEntityDescription(
        key="cost_total",
        translation_key="cost_total",
        name="Cost Total",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: data.cost_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="refuelling_payment",
        translation_key="refuelling_payment",
        name="Refuelling Payment Method",
        icon="mdi:credit-card-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            data.last_refuelling.payment if data.last_refuelling else None
        ),
    ),
    # --- Tank estimate -----------------------------------------------------
    DrivvoSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        name="Fuel Level",
        icon="mdi:gauge",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.fuel_level,
        suggested_display_precision=0,
    ),
    DrivvoSensorEntityDescription(
        key="fuel_remaining",
        translation_key="fuel_remaining",
        name="Fuel Remaining",
        icon="mdi:fuel",
        state_class=SensorStateClass.MEASUREMENT,
        device_class_fn=lambda data: {
            SensorDeviceClass.VOLUME: SensorDeviceClass.VOLUME_STORAGE,
            SensorDeviceClass.ENERGY: SensorDeviceClass.ENERGY_STORAGE,
        }.get(_volume_device_class(data)),
        unit_fn=lambda data: data.volume_unit,
        value_fn=lambda data: data.fuel_remaining,
        suggested_display_precision=1,
    ),
    DrivvoSensorEntityDescription(
        key="fuel_range",
        translation_key="fuel_range",
        name="Range",
        icon="mdi:map-marker-distance",
        state_class=SensorStateClass.MEASUREMENT,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.fuel_range,
        suggested_display_precision=0,
    ),
    DrivvoSensorEntityDescription(
        key="tank_volume",
        translation_key="tank_volume",
        name="Tank Volume",
        icon="mdi:propane-tank-outline",
        entity_registry_enabled_default=False,
        device_class_fn=_volume_device_class,
        unit_fn=lambda data: data.volume_unit,
        value_fn=lambda data: data.tank_volume,
    ),
    DrivvoSensorEntityDescription(
        key="license_plate",
        translation_key="license_plate",
        name="License Plate",
        icon="mdi:card-text-outline",
        value_fn=lambda data: data.placa,
    ),
    # --- Electric ----------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="charge_battery_start",
        translation_key="charge_battery_start",
        name="Charge Battery Start",
        icon="mdi:battery-arrow-down",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: (
            data.last_refuelling.battery_start if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="charge_battery_end",
        translation_key="charge_battery_end",
        name="Charge Battery End",
        icon="mdi:battery-arrow-up",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: (
            data.last_refuelling.battery_end if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="charge_duration",
        translation_key="charge_duration",
        name="Charge Duration",
        icon="mdi:timer-outline",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda data: (
            data.last_refuelling.duration if data.last_refuelling else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="charge_energy",
        translation_key="charge_energy",
        name="Charge Energy",
        icon="mdi:lightning-bolt",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="kWh",
        value_fn=lambda data: data.charge_energy,
        suggested_display_precision=2,
    ),
    # --- Services ----------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="service_place",
        translation_key="service_place",
        name="Service Place",
        icon="mdi:map-marker",
        value_fn=lambda data: data.last_service.place if data.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_odometer",
        translation_key="expense_odometer",
        name="Expense Odometer",
        icon="mdi:speedometer",
        entity_registry_enabled_default=False,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.last_expense.odometer if data.last_expense else None,
    ),
    # --- Incomes -----------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="income_total",
        translation_key="income_total",
        name="Income Total",
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.income_total,
    ),
    DrivvoSensorEntityDescription(
        key="income_date",
        translation_key="income_date",
        name="Income Date",
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_income.date if data.last_income else None,
    ),
    DrivvoSensorEntityDescription(
        key="income_value",
        translation_key="income_value",
        name="Income Value",
        icon="mdi:cash-plus",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: (
            data.last_income.total_value if data.last_income else None
        ),
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="income_value_total",
        translation_key="income_value_total",
        name="Income Value Total",
        icon="mdi:cash-plus",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda data: data.currency,
        value_fn=lambda data: data.income_value_total,
        suggested_display_precision=2,
    ),
    # --- Routes ------------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="route_total",
        translation_key="route_total",
        name="Route Total",
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.route_total,
    ),
    DrivvoSensorEntityDescription(
        key="route_distance_total",
        translation_key="route_distance_total",
        name="Route Distance Total",
        icon="mdi:road-variant",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.route_distance_total,
    ),
    # --- Readings ----------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="reading_total",
        translation_key="reading_total",
        name="Reading Total",
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.reading_total,
    ),
    DrivvoSensorEntityDescription(
        key="reading_date",
        translation_key="reading_date",
        name="Reading Date",
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_reading.date if data.last_reading else None,
    ),
    DrivvoSensorEntityDescription(
        key="reading_odometer",
        translation_key="reading_odometer",
        name="Reading Odometer",
        icon="mdi:speedometer",
        entity_registry_enabled_default=False,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: data.last_reading.odometer if data.last_reading else None,
    ),
    # --- Checklists --------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="checklist_total",
        translation_key="checklist_total",
        name="Checklist Total",
        icon="mdi:clipboard-check-outline",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.checklist_total,
    ),
    DrivvoSensorEntityDescription(
        key="checklist_date",
        translation_key="checklist_date",
        name="Checklist Date",
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_checklist.date if data.last_checklist else None,
    ),
    # --- Reminders ---------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="reminder_next_description",
        translation_key="reminder_next_description",
        name="Next Reminder",
        icon="mdi:bell-ring-outline",
        value_fn=lambda data: (
            data.next_reminder["description"] if data.next_reminder else None
        ),
        attributes_fn=reminder_attributes,
    ),
    DrivvoSensorEntityDescription(
        key="reminder_next_date",
        translation_key="reminder_next_date",
        name="Next Reminder Date",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: (
            data.next_reminder["date"] if data.next_reminder else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="reminder_next_odometer",
        translation_key="reminder_next_odometer",
        name="Next Reminder Odometer",
        icon="mdi:speedometer",
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: (
            data.next_reminder["odometer"] if data.next_reminder else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="reminder_next_days",
        translation_key="reminder_next_days",
        name="Next Reminder Days",
        icon="mdi:calendar-range",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda data: (
            data.next_reminder["days_left"] if data.next_reminder else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="reminder_next_distance",
        translation_key="reminder_next_distance",
        name="Next Reminder Distance",
        icon="mdi:road",
        state_class=SensorStateClass.MEASUREMENT,
        device_class_fn=_distance_device_class,
        unit_fn=lambda data: data.distance_unit,
        value_fn=lambda data: (
            data.next_reminder["distance_left"] if data.next_reminder else None
        ),
    ),
    DrivvoSensorEntityDescription(
        key="reminders_total",
        translation_key="reminders_total",
        name="Reminders Total",
        icon="mdi:bell-outline",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.reminders_total,
    ),
    DrivvoSensorEntityDescription(
        key="reminders_overdue",
        translation_key="reminders_overdue",
        name="Reminders Overdue",
        icon="mdi:bell-alert-outline",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.reminders_overdue,
    ),
    # --- Account -----------------------------------------------------------
    DrivvoSensorEntityDescription(
        key="driver_license_expiry",
        translation_key="driver_license_expiry",
        name="Driver License Expiry",
        icon="mdi:card-account-details-outline",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.driver_license_expiry,
    ),
)
