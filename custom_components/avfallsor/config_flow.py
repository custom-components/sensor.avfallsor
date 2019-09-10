"""Adds config flow for nordpool."""
import logging
from collections import OrderedDict

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback


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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AvfallsorOptionsHandler(config_entry)


class AvfallsorOptionsHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self._errors = {}

    async def async_step_init(self, user_input=None):
        _LOGGER.info("user input %r" % user_input)

        #_LOGGER.info('options %r' % dict(self.config_entry.options))
        #_LOGGER.info('data %r' % dict(self.config_entry.data))

        old_settings = self.config_entry.data

        if user_input is not None:
            _LOGGER.info('shit isnt none')
            if user_input != old_settings:
                # There some stuff that are changed.
                user_input = old_settings.update(user_input)
            else:
                _LOGGER.info('didnt update settings as they where the same as the old one.')

            if user_input:
                _LOGGER.info('should have created new entry')
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="edit",
            data_schema=vol.Schema(
                create_schema()


            ),
            errors=self._errors
        )

    async def _show_config_form(self, user_input=None):
        pass
        # https://github.com/thomasloven/hass-favicon/blob/master/custom_components/favicon/__init__.py#L25
        #
        # hass.config_entries.async_update_entry(self.config_entry, options=options)
