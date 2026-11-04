"""Drivvo data update coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from . import calc
from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import DOMAIN, SCAN_INTERVAL
from .dates import parse_api_datetime
from .models import VehicleData

_LOGGER = logging.getLogger(__name__)


class DrivvoDataUpdateCoordinator(DataUpdateCoordinator[VehicleData]):
    """Per-vehicle coordinator. Reuses one client (and its token) per config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DrivvoApiClient,
        vehicle_id: int,
        update_interval: timedelta | None = None,
    ) -> None:
        if update_interval is None:
            update_interval = SCAN_INTERVAL
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_vehicle_{vehicle_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.vehicle_id = vehicle_id

    async def _async_update_data(self) -> VehicleData:
        if self.client.token is None:
            try:
                await self.client.login()
            except DrivvoAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DrivvoApiError as err:
                raise UpdateFailed(str(err)) from err

        try:
            return self._with_reminders(await self.client.get_vehicle(self.vehicle_id))
        except DrivvoAuthError:
            self.client.token = None
            try:
                await self.client.login()
            except DrivvoAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DrivvoApiError as err:
                raise UpdateFailed(str(err)) from err
            try:
                return self._with_reminders(
                    await self.client.get_vehicle(self.vehicle_id)
                )
            except DrivvoAuthError as err:
                # Fresh token still rejected — credentials likely changed
                raise ConfigEntryAuthFailed(str(err)) from err
            except DrivvoApiError as err:
                raise UpdateFailed(str(err)) from err
        except DrivvoApiError as err:
            raise UpdateFailed(str(err)) from err

    def _with_reminders(self, data: VehicleData) -> VehicleData:
        """Attach the due-date predictions.

        Drivvo stores only the repetition rule; the due date is derived from the
        last entry of the watched type, which is why it happens here rather than
        in the API client.
        """
        data.reminders = sorted(
            calc.reminder_predictions(
                data.reminders_raw,
                [
                    {
                        "data": e.date,
                        "odometro": e.odometer,
                        "tipos_despesa": [
                            {"id_tipo_despesa": tid} for tid in e.type_ids
                        ],
                    }
                    for e in data.expenses
                ],
                [
                    {
                        "data": s.date,
                        "odometro": s.odometer,
                        "tipos_servico": [
                            {"id_tipo_servico": tid} for tid in s.type_ids
                        ],
                    }
                    for s in data.services
                ],
                data.odometer,
                now=dt_util.now(),
                parse_datetime=parse_api_datetime,
            ),
            key=calc.sort_key_reminder,
        )
        return data
