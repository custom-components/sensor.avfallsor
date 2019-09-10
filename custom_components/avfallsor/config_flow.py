"""Adds config flow for nordpool."""
import logging
from collections import OrderedDict

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries

from . import DOMAIN, garbage_types

_LOGGER = logging.getLogger(__name__)


def create_schema():
    data_schema = OrderedDict()
    data_schema[vol.Optional("address", default="", description="address")] = str
    data_schema[vol.Optional("street_id", default="", description="street_id")] = str
    data_schema[vol.Optional("kommune", default="", description="kommune")] = str

    for gbt in garbage_types:
        data_schema[vol.Optional(gbt, default=True, description=gbt)] = bool

    return data_schema


@config_entries.HANDLERS.register(DOMAIN)
class AvfallSorFlowHandler(config_entries.ConfigFlow):
    """Config flow for Blueprint."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(
        self, user_input=None
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            gbt = []
            for key, value in dict(user_input).items():
                if key in garbage_types and value is True:
                    gbt.append(key)
                    user_input.pop(key)

            if len(gbt):
                user_input["garbage_types"] = gbt
            # Think the title is wrong..
            return self.async_create_entry(title="avfallsor", data=user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit location data."""

        data_schema = create_schema()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(data_schema), errors=self._errors
        )

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        return self.async_create_entry(title="configuration.yaml", data={})
