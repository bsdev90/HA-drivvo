"""Binary sensor platform for the Drivvo integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import DOMAIN
from .coordinator import DrivvoDataUpdateCoordinator
from .entity import DrivvoEntity
from .models import VehicleData
from .sensors import reminder_attributes


@dataclass
class DrivvoBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Drivvo binary sensor entities."""

    value_fn: Callable[[VehicleData], bool | None] | None = None
    attributes_fn: Callable[[VehicleData], dict[str, Any]] | None = None


BINARY_SENSOR_TYPES: tuple[DrivvoBinarySensorEntityDescription, ...] = (
    DrivvoBinarySensorEntityDescription(
        key="maintenance_due",
        translation_key="maintenance_due",
        name="Maintenance Due",
        icon="mdi:car-wrench",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.reminders_overdue > 0,
        attributes_fn=reminder_attributes,
    ),
    DrivvoBinarySensorEntityDescription(
        key="tank_full",
        translation_key="tank_full",
        name="Last Refuelling Full Tank",
        icon="mdi:gas-station",
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            data.last_refuelling.tank_full if data.last_refuelling else None
        ),
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the binary sensor platform."""
    # Yield once: HA framework requires async signature even though body is sync.
    await asyncio.sleep(0)
    store = hass.data[DOMAIN][config_entry.entry_id]
    coordinators: dict[str, DrivvoDataUpdateCoordinator] = store["coordinators"]

    entities = []
    for coordinator in coordinators.values():
        vehicle_data = coordinator.data
        if vehicle_data is None:
            continue
        entities.extend(
            DrivvoBinarySensorEntity(
                coordinator,
                description,
                vehicle_data.id,
                vehicle_data.identification,
            )
            for description in BINARY_SENSOR_TYPES
        )

    async_add_entities(entities)


class DrivvoBinarySensorEntity(DrivvoEntity, BinarySensorEntity):
    """Representation of a Drivvo binary sensor."""

    entity_description: DrivvoBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return true when the condition is active."""
        if self.coordinator.data is None or not self.entity_description.value_fn:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the extra attributes this binary sensor exposes."""
        if (
            self.coordinator.data is not None
            and self.entity_description.attributes_fn is not None
        ):
            return self.entity_description.attributes_fn(self.coordinator.data)
        return None
