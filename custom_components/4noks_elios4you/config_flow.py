"""Config Flow for 4-noks Elios4You.

https://github.com/alexdelprete/ha-4noks-elios4you
"""

import ipaddress
import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import selector

from .api import Elios4YouAPI
from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PERSISTENT_CONNECTION,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PERSISTENT_CONNECTION,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Empty Error Class."""


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(x and not disallowed.search(x) for x in host.split("."))


@callback
def get_host_from_config(hass: HomeAssistant):
    """Return the hosts already configured."""
    return {
        config_entry.data.get(CONF_HOST)
        for config_entry in hass.config_entries.async_entries(DOMAIN)
    }


class Elios4YouConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """4-noks Elios4You config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Initiate Options Flow Instance."""
        return Elios4YouOptionsFlow(config_entry)

    def _host_in_configuration_exists(self, host) -> bool:
        """Return True if host exists in configuration."""
        if host in get_host_from_config(self.hass):
            return True
        return False

    async def test_connection(self, name, host, port, scan_interval):
        """Return true if credentials is valid."""
        _LOGGER.debug(f"Test connection to {host}:{port}")
        try:
            _LOGGER.debug("Creating API Client")
            self.api = Elios4YouAPI(self.hass, name, host, port, scan_interval)
            _LOGGER.debug("API Client created: calling get data")
            self.api_data = await self.api.async_get_data()
            _LOGGER.debug("API Client: get data")
            _LOGGER.debug(f"API Client Data: {self.api_data}")
            return self.api.data["sn"]
        except ConnectionError as connerr:
            _LOGGER.error(
                f"Failed to connect to host: {host}:{port} - Exception: {connerr}"
            )
            return False

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            scan_interval = user_input[CONF_SCAN_INTERVAL]

            if self._host_in_configuration_exists(host):
                errors[CONF_HOST] = "Device Already Configured"
            elif not host_valid(user_input[CONF_HOST]):
                errors[CONF_HOST] = "invalid Host IP"
            else:
                uid = await self.test_connection(name, host, port, scan_interval)
                if uid is not False:
                    _LOGGER.debug(f"Device unique id: {uid}")
                    await self.async_set_unique_id(uid)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )
                else:
                    errors[
                        CONF_HOST
                    ] = "Connection to device failed (S/N not retreived)"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=DEFAULT_NAME,
                    ): cv.string,
                    vol.Required(
                        CONF_HOST,
                    ): cv.string,
                    vol.Required(
                        CONF_PORT,
                        default=DEFAULT_PORT,
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=DEFAULT_SCAN_INTERVAL,
                    ): selector(
                        {
                            "number": {
                                "min": 30,
                                "max": 600,
                                "step": 10,
                                "unit_of_measurement": "s",
                                "mode": "slider",
                            }
                        }
                    ),
                    vol.Optional(
                        CONF_PERSISTENT_CONNECTION,
                        default=DEFAULT_PERSISTENT_CONNECTION,
                    ): bool,
                },
            ),
            errors=errors,
        )


class Elios4YouOptionsFlow(config_entries.OptionsFlow):
    """Config flow options handler."""

    VERSION = 1

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize option flow instance."""
        self.config_entry = config_entry
        self.data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=self.config_entry.data.get(CONF_HOST),
                ): cv.string,
                vol.Required(
                    CONF_PORT,
                    default=self.config_entry.data.get(CONF_PORT),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.data.get(CONF_SCAN_INTERVAL),
                ): selector(
                    {
                        "number": {
                            "min": 30,
                            "max": 600,
                            "step": 10,
                            "unit_of_measurement": "s",
                            "mode": "slider",
                        }
                    }
                ),
                vol.Optional(
                    CONF_PERSISTENT_CONNECTION,
                    default=DEFAULT_PERSISTENT_CONNECTION,
                ): bool,
            }
        )

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            # complete non-edited entries before update (ht @PeteRage)
            if CONF_NAME in self.config_entry.data:
                user_input[CONF_NAME] = self.config_entry.data.get(CONF_NAME)

            # write updated config entries (ht @PeteRage / @fuatakgun)
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input, options=self.config_entry.options
            )
            self.async_abort(reason="configuration updated")

            # write empty options entries (ht @PeteRage / @fuatakgun)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=self.data_schema)
