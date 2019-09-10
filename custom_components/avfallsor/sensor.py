import logging

from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.const import ATTR_ATTRIBUTION

from . import DOMAIN, garbage_types
from .utils import (
    find_address,
    find_address_from_lat_lon,
    to_dt,
    find_next_garbage_pickup,
    parse_tomme_kalender,
)


_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional("address", default=""): cv.string,
        vol.Optional("street_id", default=""): cv.string,
        vol.Optional("kommune", default=""): cv.string,
        vol.Optional("garbage_types", default=garbage_types): list,
    }
)


MIN_TIME_BETWEEN_UPDATES = timedelta(weeks=4)


def check_settings(config, hass):
    if not any(config.get(i) for i in ["street_id", "kommune"]):
        _LOGGER.info("street_id or kommune was not set config")
    else:
        return True
    if not config.get("address"):
        _LOGGER.info("address was not set")
    else:
        return True

    if not hass.config.latitude or not hass.config.longitude:
        _LOGGER.info("latitude and longitude is not set in ha settings.")
    else:
        return True

    raise vol.Invalid("Missing settings to setup the sensor.")


async def async_setup_platform(
    hass, config_entry, async_add_devices, discovery_info=None
):
    """Setup sensor platform for the ui"""
    config = config_entry
    street_id = config.get("street_id")
    kommune = config.get("kommune")
    address = config.get("address")

    check_settings(config, hass)
    data = AvfallSorData(
        address,
        street_id,
        kommune,
        hass.config.latitude,
        hass.config.longitude,
        async_get_clientsession(hass),
    )

    await data.update()
    sensors = []
    for gb_type in config.get("garbage_types"):
        sensor = AvfallSor(data, gb_type)
        sensors.append(sensor)

    async_add_devices(sensors)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    street_id = config.get("street_id")
    kommune = config.get("kommune")
    address = config.get("address")
    check_settings(config, hass)
    data = AvfallSorData(
        address,
        street_id,
        kommune,
        hass.config.latitude,
        hass.config.longitude,
        async_get_clientsession(hass),
    )
    await data.update()

    sensors = []
    for gb_type in config.get("garbage_types", garbage_types):
        sensor = AvfallSor(data, gb_type)
        sensors.append(sensor)

    async_add_devices(sensors)
    return True


async def async_remove_entry(hass, config_entry):
    _LOGGER.info("async_remove_entry avfallsor")
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
        _LOGGER.info("Successfully removed sensor from the avfallsor integration")
    except ValueError:
        pass


class AvfallSorData:
    def __init__(self, address, street_id, kommune, lat, lon, client):
        self._address = address
        self._street_id = street_id
        self._kommune = kommune
        self.client = client
        self._data = {}
        self._last_update = None
        self._grbrstr = None
        self._lat = lat
        self._lon = lon
        self._friendly_name = None

    async def find_street_id(self):
        """Helper to get get the correct info with the least possible setup

           Find the info using different methods where the prios are:
           1. streetid and kommune
           2. address
           3. lat and lon set in ha config when this was setup.

        """
        if not len(self._street_id) and not len(self._kommune):
            if self._address and self._grbrstr is None:
                result = await find_address(self._address, self.client)
                if result:
                    self._grbrstr = result
                    return
            if self._lat and self._lon and self._grbrstr is None:
                result = await find_address_from_lat_lon(
                    self._lat, self._lon, self.client
                )
                if result:
                    self._grbrstr = result
                    return

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        _LOGGER.info("Fetching stuff for AvfallSorData")
        await self.find_street_id()
        if self._street_id and self._kommune:
            url = f"https://avfallsor.no/tommekalender/?id={self._street_id}&kommune={self._kommune}"
        elif self._grbrstr:
            # This seems to redirect to the url above.
            url = f"https://avfallsor.no/tommekalender/?gbnr={self._grbrstr}.&searchString=&mnr=&type=adrSearchBtn&pappPapirPlast=true&glassMetall=true"
        resp = await self.client.get(url)
        if resp.status == 200:
            text = await resp.text()
            self._data = parse_tomme_kalender(text)
            self._last_update = datetime.now()

    async def update(self):
        await self._update()
        return self._data


class AvfallSor(Entity):
    def __init__(self, data, garbage_type):
        self.data = data
        self._garbage_type = garbage_type

    @property
    def state(self):
        """Return the state of the sensor."""
        nxt = self.next_garbage_pickup
        if nxt is not None:
            delta = nxt.date() - datetime.today().date()
            return delta.days

    async def async_update(self):
        await self.data.update()

    @property
    def next_garbage_pickup(self):
        """Get the date of the next picked for that garbage type."""
        if self._garbage_type == "paper":
            return find_next_garbage_pickup(self.data._data.get("paper"))

        elif self._garbage_type == "bio":
            return find_next_garbage_pickup(self.data._data.get("bio"))

        elif self._garbage_type == "mixed":
            return find_next_garbage_pickup(self.data._data.get("rest"))

        elif self._garbage_type == "metal":
            return find_next_garbage_pickup(self.data._data.get("metal"))

    @property
    def icon(self) -> str:
        """Shows the correct icon for container."""
        # todo fix icons.
        if self._garbage_type == "paper":
            return "mdi:recycle"

        elif self._garbage_type == "bio":
            return "mdi:recycle"

        elif self._garbage_type == "mixed":
            return "mdi:recycle"

        elif self._garbage_type == "metal":
            return "mdi:recycle"

    @property
    def unique_id(self) -> str:
        """Return the name of the sensor."""
        return f"avfallsor_{self._garbage_type}_{self.data._street_id or self.data._grbrstr}"

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def device_state_attributes(self) -> dict:
        """Return the state attributes."""
        return {
            "next garbage pickup": self.next_garbage_pickup,
            ATTR_ATTRIBUTION: "avfallsør",
            "last update": self.data._last_update,
        }

    @property
    def device_info(self) -> dict:
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def unit(self)-> int:
        """Unit"""
        return int

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "days"

    @property
    def friendly_name(self) -> str:
        return self._friendly_name
