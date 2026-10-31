import asyncio
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import (
    CONF_EMAIL,
    CONF_ID_VEHICLE,
    CONF_MODEL,
    CONF_PASSWORD,
    DOMAIN,
    ICON,
)
from .coordinator import DrivvoDataUpdateCoordinator
from .dates import parse_api_datetime
from .entity import DrivvoEntity
from .sensors import SENSOR_TYPES, DrivvoSensorEntityDescription

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_MODEL): cv.string,
        vol.Required(CONF_ID_VEHICLE): cv.string,
    }
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
) -> None:
    """Setup sensor platform."""
    # Yield once: HA framework requires async signature even though body is sync.
    await asyncio.sleep(0)
    store = hass.data[DOMAIN][config_entry.entry_id]
    coordinators: dict[str, DrivvoDataUpdateCoordinator] = store["coordinators"]

    entities = []
    for coordinator in coordinators.values():
        vehicle_data = coordinator.data
        if vehicle_data is None:
            continue
        for description in SENSOR_TYPES:
            if description.key == "vehicle":
                entities.append(
                    DrivvoSensorEntity(
                        coordinator,
                        description,
                        vehicle_data.id,
                        vehicle_data.identification,
                        vehicle_data.model,
                    )
                )
            else:
                entities.append(
                    DrivvoSensorEntity(
                        coordinator,
                        description,
                        vehicle_data.id,
                        vehicle_data.identification,
                    )
                )

    async_add_entities(entities)


async def async_setup_platform(
    hass: core.HomeAssistant,
    config: dict[str, Any],
    add_entities,
    discovery_info=False,
) -> bool:
    """Import to config flow."""
    _LOGGER.warning(
        "Configuration of Drivvo integration via YAML is deprecated."
        "Your configuration has been imported into the UI and can be"
        "removed from the configuration.yaml file."
    )

    async_create_issue(
        hass,
        DOMAIN,
        "yaml_deprecated",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="yaml_deprecated",
    )

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data=config,
        )
    )

    return True


class DrivvoSensorEntity(DrivvoEntity, SensorEntity):
    """Representation of a Drivvo sensor."""

    entity_description: DrivvoSensorEntityDescription

    def __init__(
        self,
        coordinator: DrivvoDataUpdateCoordinator,
        description: DrivvoSensorEntityDescription,
        vehicle_id: str,
        vehicle_name: str,
        model: str | None = None,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator, description, vehicle_id, vehicle_name)
        self._model = model

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return STATE_UNKNOWN

        if self.entity_description.key == "vehicle" and self._model:
            return self._model

        if not self.entity_description.value_fn:
            return STATE_UNKNOWN

        try:
            value = self.entity_description.value_fn(self.coordinator.data)
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.error(
                "Error getting value for %s: %s", self.entity_description.key, err
            )
            return STATE_UNKNOWN

        if self.device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
            # Drivvo reports dates in the account's local time, not UTC.
            return parse_api_datetime(value)

        return value

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class, which can depend on the account units."""
        if (
            self.coordinator.data is not None
            and self.entity_description.device_class_fn is not None
        ):
            return self.entity_description.device_class_fn(self.coordinator.data)
        return self.entity_description.device_class

    @property
    def icon(self) -> str:
        """Return the icon."""
        return self.entity_description.icon or ICON

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity."""
        if (
            self.coordinator.data is not None
            and self.entity_description.unit_fn is not None
        ):
            return self.entity_description.unit_fn(self.coordinator.data)
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the extra attributes this sensor exposes."""
        if (
            self.coordinator.data is not None
            and self.entity_description.attributes_fn is not None
        ):
            return self.entity_description.attributes_fn(self.coordinator.data)
        return None
