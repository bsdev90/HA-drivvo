"""Diagnostics for the Drivvo integration."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "placa", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    # Yield once: HA framework requires async signature even though body is sync.
    await asyncio.sleep(0)
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    vehicles: dict[str, Any] = {}
    for vid, coord in store.get("coordinators", {}).items():
        d = coord.data
        if d is None:
            continue
        vehicles[str(vid)] = {
            "id": d.id,
            "name": d.name,
            "manufacturer": d.manufacturer,
            "model": d.model,
            "distance_unit": d.distance_unit,
            "currency": d.currency,
            "refuelling_count": len(d.refuellings),
            "service_count": len(d.services),
            "expense_count": len(d.expenses),
            "income_count": len(d.incomes),
            "route_count": len(d.routes),
            "reading_count": len(d.readings),
            "checklist_count": len(d.checklists),
            "reminder_count": d.reminders_total,
            "reminders_overdue": d.reminders_overdue,
            "volume_unit": d.volume_unit,
            "efficiency_unit": d.efficiency_unit,
            "tank_volume": d.tank_volume,
            "odometer": d.odometer,
            "odometer_date": d.odometer_date,
        }
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "vehicles": vehicles,
    }
