"""Drivvo integration setup."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import (
    CONF_EMAIL,
    CONF_ID_VEHICLE,
    CONF_PASSWORD,
    CONF_VEHICLES,
    DOMAIN,
    SCAN_INTERVAL,
)
from .coordinator import DrivvoDataUpdateCoordinator
from .services import async_setup_services, async_unload_services

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = DrivvoApiClient(
        session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await client.login()
    except DrivvoAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DrivvoApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinators: dict[str, DrivvoDataUpdateCoordinator] = {}
    for vehicle_id in entry.data.get(CONF_VEHICLES, []) or []:
        vid_str = str(vehicle_id)
        vid_int = int(vehicle_id)
        coord = DrivvoDataUpdateCoordinator(
            hass, client, vid_int, update_interval=SCAN_INTERVAL
        )
        try:
            await coord.async_config_entry_first_refresh()
        except (UpdateFailed, ConfigEntryNotReady) as err:
            _LOGGER.warning(
                "Vehicle %s could not be loaded: %s — skipping", vid_str, err
            )
            async_create_issue(
                hass,
                DOMAIN,
                f"{vid_str}_vehicle_non_existent",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="vehicle_non_existent",
                translation_placeholders={"vehicle": vid_str},
            )
            continue
        async_delete_issue(hass, DOMAIN, f"{vid_str}_vehicle_non_existent")
        coordinators[vid_str] = coord

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinators": coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            async_unload_services(hass)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Yield once: HA framework requires async signature even though body is sync.
    await asyncio.sleep(0)
    _LOGGER.debug("Migrating from version %s", entry.version)
    if entry.version == 1:
        data = {
            CONF_EMAIL: entry.data.get(CONF_EMAIL),
            CONF_PASSWORD: entry.data.get(CONF_PASSWORD),
            CONF_VEHICLES: [entry.data.get(CONF_ID_VEHICLE)],
        }
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    _LOGGER.info("Migration to version %s successful", entry.version)
    return True
