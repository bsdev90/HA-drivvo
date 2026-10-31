"""Base entity for the Drivvo integration."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import DrivvoDataUpdateCoordinator


class DrivvoEntity(CoordinatorEntity[DrivvoDataUpdateCoordinator]):
    """Device wiring shared by every Drivvo platform."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: DrivvoDataUpdateCoordinator,
        description: EntityDescription,
        vehicle_id: str,
        vehicle_name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._vehicle_id = vehicle_id
        self._vehicle_name = vehicle_name
        self._attr_unique_id = f"{vehicle_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=dr.DeviceEntryType.SERVICE,
            # Kept as str(vehicle_id) so existing devices are not orphaned.
            identifiers={(DOMAIN, str(vehicle_id))},
            name=vehicle_name,
            manufacturer="Drivvo",
            model=f"{coordinator.data.manufacturer} {coordinator.data.model}",
        )
