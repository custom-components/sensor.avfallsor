import logging
import re

from collections import defaultdict
from datetime import datetime, date, timedelta


import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.const import ATTR_ATTRIBUTION

from . import DOMAIN, garbage_types


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



PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("streetid", default=""): cv.string,
        vol.Required("kommune", default=""): cv.string,
        vol.Optional("garbage_types", default=garbage_types): list,
    }
)


MIN_TIME_BETWEEN_UPDATES = timedelta(weeks=4)


async def async_setup_platform(
    hass, config_entry, async_add_devices, discovery_info=None
):
    """Setup sensor platform for the ui"""
    config = config_entry
    streetid = config.get("streetid")
    kommune = config.get("kommune")
    data = AvfallSorData(streetid, kommune, async_get_clientsession(hass))
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
    streetid = config.get("streetid")
    kommune = config.get("kommune")
    data = AvfallSorData(streetid, kommune, async_get_clientsession(hass))
    sensors = []
    for gb_type in config.get("garbage_types"):
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


def find_next_garbage_pickup(dates):
    if dates is None:
        return

    today = datetime.now().date()
    for i in sorted(dates):
        if i.date() >= today:
            return i


def to_dt(s):
    # if a year is missing we assume it is this year.
    # this seems to only be a issue with the tomme exceptions.
    if not re.search(r"\d{4}", s):
        s = "%s %s" % (s, date.today().year)

    for key, value in nor_days.items():
        if key.lower() in s.lower():
            s = s.replace(key, value)

    for k, v in nor_months.items():
        if k.lower() in s.lower():
            s = s.replace(k, v)

    return datetime.strptime(s.strip(), "%A %d. %b %Y")


def parse_tomme_kalender(text):
    """Parse the avfallsør tømme kalender to a dict."""
    from bs4 import BeautifulSoup

    exceptions = defaultdict(list)
    tomme_days = defaultdict(list)
    soup = BeautifulSoup(text, "html.parser")
    tmk = soup.select("ul.tmk > li")
    tommeday_soup = soup.find(
        text=re.compile(
            r"Din tømmedag er: (Mandag|Tirsdag|Onsdag|Torsdag|Fredag|Lørdag|Søndag)",
            re.IGNORECASE,
        )
    )
    tomme_day = tommeday_soup.split(":")[1].strip()
    tomme_days["tomme_day"] = tomme_day
    tomme_day_nr = list(nor_days.keys()).index(tomme_day)
    for li in tmk:
        if "grønn" in li.img.get("alt", ""):
            tomme_days["paper"].append(to_dt(li.text.strip()))
        elif "glass" in li.img.get("alt", ""):
            tomme_days["metal"].append(to_dt(li.text.strip()))
        # Grab the tomme exceptions
        if "tømmes" in li.text:
            for item in li.select("img"):
                old, new = li.text.strip().split("tømmes")
                if "Bio" in item["src"]:
                    exceptions["bio"].append((to_dt(old), to_dt(new)))
                elif "Rest" in item["src"]:
                    exceptions["rest"].append((to_dt(old), to_dt(new)))

    # Lets get all the days for the year.
    today = date.today()
    start_of_year = datetime(today.year, 1, 1)
    for i in range(0, 365):
        i_date = start_of_year + timedelta(days=i)
        if i_date.weekday() == tomme_day_nr:
            tomme_days["bio"].append(i_date)
            tomme_days["rest"].append(i_date)

    # replace any exception from the normals tommedays
    # this usually because of holydays etc.
    for item in tomme_days["rest"]:
        for i in exceptions["rest"]:
            if i and i[0] == item:
                tomme_days["rest"].remove(item)
                tomme_days["rest"].append(i[1])

    for item in tomme_days["bio"]:
        for i in exceptions["bio"]:
            if i and i[0] == item:
                tomme_days["bio"].remove(item)
                tomme_days["bio"].append(i[1])

    return tomme_days


class AvfallSorData:
    def __init__(self, streetid, kommune, client):
        self._streetid = streetid
        self._kommune = kommune
        self.client = client
        self._data = {}
        self._last_update = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def _update(self):
        _LOGGER.info("Fetching stuff for AvfallSorData")
        url = f"https://avfallsor.no/tommekalender/?id={self._streetid}&kommune={self._kommune}"
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
        if self._garbage_type == "paper":
            return find_next_garbage_pickup(self.data._data.get("paper"))

        elif self._garbage_type == "bio":
            return find_next_garbage_pickup(self.data._data.get("bio"))

        elif self._garbage_type == "mixed":
            return find_next_garbage_pickup(self.data._data.get("rest"))

        elif self._garbage_type == "metal":
            return find_next_garbage_pickup(self.data._data.get("metal"))

    @property
    def icon(self):
        """Shows the correct icon for container."""
        # todo fix icons.
        # "mdi:recycle"
        if self._garbage_type == "paper":
            return "green"

        elif self._garbage_type == "bio":
            return "brown"

        elif self._garbage_type == "general_waste":
            return "grey"

        elif self._garbage_type == "metal":
            return "reddish"  # what color is the box??

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"avfallsor_{self._garbage_type}"

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            "next garbage pickup": self.next_garbage_pickup,
            ATTR_ATTRIBUTION: "avfallsør",
            "last update": self.data._last_update,
        }

    @property
    def device_info(self):
        """I can't remember why this was needed :D"""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": "someone",
        }

    @property
    def unit(self):
        """Unit"""
        return "days"
