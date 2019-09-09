import logging

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant


DOMAIN = "avfallsor"
NAME = DOMAIN
VERSION = "0.0.1"
ISSUEURL = "https://github.com/hellowlol/sensor.avfallsor/issues"

STARTUP = """
-------------------------------------------------------------------
{name}
Version: {version}
This is a custom component
If you have any issues with this you need to open an issue here:
{issueurl}
-------------------------------------------------------------------
""".format(
    name=NAME, version=VERSION, issueurl=ISSUEURL
)

garbage_types = ["paper", "bio", "mixed", "metal"]

_LOGGER = logging.getLogger(__name__)


nor_months = {
    "jan": "jan",
    "feb": "feb",
    "mar": "mar",
    "apr": "apr",
    "mai": "may",
    "jun": "jun",
    "jul": "jul",
    "aug": "aug",
    "sep": "sep",
    "okt": "oct",
    "nov": "nov",
    "des": "dec",
}


nor_days = {
    "Mandag": "Monday",
    "Tirsdag": "Tuesday",
    "Onsdag": "Wednesday",
    "Torsdag": "Thursday",
    "Fredag": "Friday",
    "Lørdag": "Saturday",
    "Søndag": "Sunday",
}

# Add this shit as they use different caps on different parts for the site..
nor_days.update({key.lower(): value.lower() for key, value in nor_days.items()})

async def async_setup(hass, config):
    """Set up this component using YAML."""
    _LOGGER.info(STARTUP)
    if config.get(DOMAIN) is None:
        # We get her if the integration is set up using config flow
        return True

    try:
        await hass.config_entries.async_forward_entry(config, "sensor")
        _LOGGER.info("Successfully added sensor from the blueprint integration")
    except ValueError:
        pass

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={}
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up avfallsor as config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "sensor")
    )
    return True


async def async_remove_entry(hass, config_entry):
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
        _LOGGER.info("Successfully removed sensor from the blueprint integration")
    except ValueError:
        pass
