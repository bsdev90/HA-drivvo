from collections.abc import Mapping
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import (
    CONF_EMAIL,
    CONF_ID_VEHICLE,
    CONF_PASSWORD,
    CONF_VEHICLES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA: vol.Schema = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class DrivvoOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options for Drivvo."""

    def __init__(self) -> None:
        """Initialize Drivvo options flow."""
        self._client: DrivvoApiClient | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""

        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = DrivvoApiClient(
                session,
                email=user_input.get(CONF_EMAIL),
                password=user_input.get(CONF_PASSWORD),
            )
            auth_ok = False
            try:
                await client.login()
                auth_ok = True
            except DrivvoAuthError:
                errors[CONF_PASSWORD] = "auth_error"
            except DrivvoApiError:
                errors["base"] = "cannot_connect"
            if auth_ok:
                vehicles = user_input.get(CONF_VEHICLES, [])

                for vehicle in self.config_entry.data.get(CONF_VEHICLES):
                    if vehicle not in vehicles:
                        device_identifiers = {(DOMAIN, vehicle)}
                        dev_reg = dr.async_get(self.hass)
                        device = dev_reg.async_get_or_create(
                            config_entry_id=self.config_entry.entry_id,
                            identifiers=device_identifiers,
                        )

                        dev_reg.async_update_device(
                            device_id=device.id,
                            remove_config_entry_id=self.config_entry.entry_id,
                        )
                        async_delete_issue(
                            self.hass,
                            DOMAIN,
                            f"{vehicle}_vehicle_non_existent",
                        )
                        _LOGGER.debug("Device %s (%s) removed", device.name, device.id)

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_EMAIL: user_input.get(CONF_EMAIL),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD),
                        CONF_VEHICLES: vehicles,
                    },
                )

                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_abort(reason="changes_successful")

        if self._client is None:
            session = async_get_clientsession(self.hass)
            self._client = DrivvoApiClient(
                session,
                email=self.config_entry.data.get(CONF_EMAIL),
                password=self.config_entry.data.get(CONF_PASSWORD),
            )
            try:
                await self._client.login()
            except DrivvoAuthError:
                errors.setdefault(CONF_PASSWORD, "auth_error")
                self._client = None
            except DrivvoApiError:
                errors["base"] = "cannot_connect"
                self._client = None
        if self._client is not None:
            try:
                vehicles = await self._client.get_vehicles()
            except DrivvoAuthError:
                errors.setdefault(CONF_PASSWORD, "auth_error")
                vehicles = []
            except DrivvoApiError:
                errors["base"] = "cannot_connect"
                vehicles = []
        else:
            vehicles = []
        resource_vehicle = {}
        for vehicle in vehicles:
            if vehicle["ativo"]:
                vehicle_name = ""
                if vehicle["nome"] is not None and vehicle["nome"] != "":
                    vehicle_name += f"{vehicle['nome']} - "
                if vehicle["placa"] is not None and vehicle["placa"] != "":
                    vehicle_name += f"{vehicle['placa']} - "
                vehicle_name += (
                    f"{vehicle['marca']}/{vehicle['modelo']} ({vehicle['id_veiculo']})"
                )
                resource_vehicle[str(vehicle["id_veiculo"])] = vehicle_name

        old_vehicles = []

        for vehicle in self.config_entry.data[CONF_VEHICLES]:
            old_vehicles.append(vehicle)

        vehicles = {
            **dict.fromkeys(old_vehicles),
            **resource_vehicle,
        }
        if len(vehicles) == 0:
            SCHEMA_VEHICLES = DATA_SCHEMA.extend(
                {
                    vol.Optional("no_vehicles"): "",
                }
            )
        else:
            SCHEMA_VEHICLES = DATA_SCHEMA.extend(
                {
                    vol.Required(CONF_VEHICLES): cv.multi_select(vehicles),
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA_VEHICLES,
                user_input or self.config_entry.data,
            ),
            errors=errors,
        )


class DrivvoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Drivvo config flow."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize Drivvo config flow."""
        self.client: DrivvoApiClient
        self.user: str
        self.password: str

    async def async_step_import(self, import_config: Dict[str, Any]) -> FlowResult:
        """Import existing configuration."""

        if (f"{DOMAIN}_{import_config.get(CONF_EMAIL)}").lower() in [
            (f"{entry.domain}_{entry.data.get(CONF_EMAIL)}").lower()
            for entry in self._async_current_entries()
        ]:
            async_create_issue(
                self.hass,
                DOMAIN,
                f"{import_config.get(CONF_EMAIL)}_import_already_configured",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="import_already_configured",
                translation_placeholders={
                    "email": str(import_config.get(CONF_EMAIL)),
                },
            )
            return self.async_abort(reason="import_failed")

        vehicles = []
        vehicles.append(import_config.get(CONF_ID_VEHICLE))
        return self.async_create_entry(
            title=import_config[CONF_EMAIL],
            data={
                CONF_EMAIL: import_config.get(CONF_EMAIL),
                CONF_PASSWORD: import_config.get(CONF_PASSWORD),
                CONF_VEHICLES: vehicles,
            },
        )

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:
            if (f"{DOMAIN}_{user_input.get(CONF_EMAIL)}").lower() in [
                (f"{entry.domain}_{entry.data.get(CONF_EMAIL)}").lower()
                for entry in self._async_current_entries()
            ]:
                return self.async_abort(reason="already_configured")

            session = async_get_clientsession(self.hass)
            client = DrivvoApiClient(
                session,
                email=user_input.get(CONF_EMAIL),
                password=user_input.get(CONF_PASSWORD),
            )
            auth_ok = False
            try:
                await client.login()
                auth_ok = True
            except DrivvoAuthError:
                errors[CONF_PASSWORD] = "auth_error"
            except DrivvoApiError:
                errors["base"] = "cannot_connect"
            if auth_ok:
                self.user = user_input.get(CONF_EMAIL)
                self.password = user_input.get(CONF_PASSWORD)
                self.client = client
                return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA,
                user_input,
            ),
            errors=errors,
        )

    async def async_step_vehicle(
        self,
        user_input=None,
    ) -> FlowResult:
        errors = {}

        if user_input is not None and CONF_VEHICLES in user_input:
            return self.async_create_entry(
                title=self.user,
                data={
                    CONF_EMAIL: self.user,
                    CONF_PASSWORD: self.password,
                    CONF_VEHICLES: user_input[CONF_VEHICLES],
                },
            )

        try:
            vehicles = await self.client.get_vehicles()
        except DrivvoAuthError:
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA,
                errors={CONF_PASSWORD: "auth_error"},
            )
        except DrivvoApiError:
            return self.async_show_form(
                step_id="vehicle",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )
        resource_vehicle = {}
        _LOGGER.debug("Veiculos: %s", vehicles)
        for vehicle in vehicles:
            if vehicle["ativo"]:
                vehicle_name = ""
                if vehicle["nome"] is not None and vehicle["nome"] != "":
                    vehicle_name += f"{vehicle['nome']} - "
                if vehicle["placa"] is not None and vehicle["placa"] != "":
                    vehicle_name += f"{vehicle['placa']} - "
                vehicle_name += (
                    f"{vehicle['marca']}/{vehicle['modelo']} ({vehicle['id_veiculo']})"
                )
                resource_vehicle[str(vehicle["id_veiculo"])] = vehicle_name

        if len(resource_vehicle) == 0:
            return self.async_create_entry(
                title=self.user,
                data={
                    CONF_EMAIL: self.user,
                    CONF_PASSWORD: self.password,
                    CONF_VEHICLES: [],
                },
            )

        return self.async_show_form(
            step_id="vehicle",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_VEHICLES): cv.multi_select(resource_vehicle),
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, data: Mapping[str, Any]) -> FlowResult:
        """Handle a reauthorization flow request."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauth dialog."""
        errors = {}
        assert self._reauth_entry
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            reauth_client = DrivvoApiClient(
                session,
                email=user_input.get(CONF_EMAIL),
                password=user_input.get(CONF_PASSWORD),
            )
            auth_ok = False
            try:
                await reauth_client.login()
                auth_ok = True
            except DrivvoAuthError:
                errors[CONF_PASSWORD] = "auth_error"
            except DrivvoApiError:
                errors["base"] = "cannot_connect"
            if auth_ok:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_EMAIL: user_input.get(CONF_EMAIL),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD),
                        CONF_VEHICLES: self._reauth_entry.data.get(CONF_VEHICLES),
                    },
                )

                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA, user_input or self._reauth_entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Options callback for Drivvo."""
        return DrivvoOptionsFlowHandler()
