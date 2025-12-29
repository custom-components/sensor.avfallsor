import json
import logging
from collections import defaultdict
from datetime import datetime
import re

from itertools import chain

import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

pattern = re.compile(
    r"""
    (?P<weekday>\w+\s)?        # Optional weekday (e.g. "Fredag ")
    (?P<day>\d{1,2})           # Day number (1 or 2 digits)
    \.?                        # Optional dot after day
    \s+                        # One or more spaces
    (?P<month>[a-z]+)          # Month name (letters only)
    \s*                        # Optional whitespace
    (?P<year>\d{4}|\d{2})?     # Optional year (2 or 4 digits)
    """,
    re.VERBOSE | re.IGNORECASE,
)


# Map Norwegian weekday names to their corresponding indices
weekday_map = {
    "mandager": 0,  # Monday
    "tirsdager": 1,  # Tuesday
    "onsdager": 2,  # Wednesday
    "torsdager": 3,  # Thursday
    "fredager": 4,  # Friday
    "lørdager": 5,  # Saturday
    "søndager": 6,  # Sunday
}

# Norwegian months mapping
months_no = {
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


gb_map = {
    "mixed": "Restavfall",
    "bio": "Matavfall",
    "paper": "Papp og papir",
    "plastic": "Plastemballasje",
    "metal": "Glass- og metallemballasje",
}
gb_map.update({v: k for k, v in gb_map.items()})


def parse_date(date_str: str, year=None):
    match = re.match(pattern, date_str.lower())

    if match:
        d = match.groupdict()
        year = year or d.get("year")
        if not year:
            year = datetime.today().year
        year = int(year)
        weekday = d.get("weekday")
        day = int(d.get("day"))
        month = d.get("month")

        res = datetime(year=year, month=months_no.get(month), day=day)
        _LOGGER.info("parse_date %r", res)
        return res


def check_settings(config, hass):
    if not any(config.get(i) for i in ["street_id"]):
        _LOGGER.debug("street_id was not set")
    else:
        return True
    if not config.get("address"):
        _LOGGER.debug("address was not set")
    else:
        return True

    if not hass.config.latitude or not hass.config.longitude:
        _LOGGER.debug("latitude and longitude is not set in ha settings.")
    else:
        return True

    raise vol.Invalid("Missing settings to setup the sensor.")


def find_next_garbage_pickup(dates):
    _LOGGER.debug("Called find_next_garbage_pickup %r", dates)
    if dates is None:
        return

    today = datetime.now().date()
    for i in sorted(dates):
        if i.date() >= today:
            return i

    return None


def check_tomme_kalender(data):
    tomme_kalender = parse_tomme_kalender(data)

    if not any(len(i) > 1 for i in tomme_kalender.values()):
        _LOGGER.debug("No tømmekalender is available")
        return False
    return True


async def verify_that_we_can_find_id(config, hass):
    client = async_get_clientsession(hass)

    try:
        # Check that we have some info we can use to find the tommeplan
        # it might still fail if the user entered the wrong adresse etc.
        check_settings(config, hass)
    except vol.Invalid:
        return False

    try:
        adr = await find_id(config.get("address"), client)
        if adr:
            return adr
    except:
        _LOGGER.exception("Failed to find the id")
        pass

    try:
        adr = await find_id_from_lat_lon(
            hass.config.latitude, hass.config.longitude, client
        )
        if adr:
            return adr
    except:
        _LOGGER.exception("Failed to find the id from lat lon")
        pass

    return False


async def find_id(address, client):
    """Find the id that avfall sør uses to create the tømmeplan"""
    _LOGGER.info("Called find_id %r", address)
    if not address:
        return

    # For some silly reason we can't seem to search for anything
    # other then streetname hournumber letter, so we remove the municipality
    # and check that against the label instead.
    if "," in address:
        cleaned_address = address.split(",")[0]
    else:
        cleaned_address = address

    params = {"lookup_term": cleaned_address}
    url = "https://avfallsor.no/wp-json/addresses/v1/address"
    resp = await client.get(url, params=params)

    _LOGGER.debug("Trying to find the id using url %s, params %s", url, params)

    if resp.status == 200:
        data = await resp.json()

        _LOGGER.debug("Raw response:\n\n %s", json.dumps(data, indent=4))
        # Api returns a empty list if we dont get a hit.
        if isinstance(data, list):
            _LOGGER.info("Didn't find address using %s", address)
            return None

        if len(data) > 1:
            _LOGGER.warning(
                "We got multiple adresses, consider extracting the id manually or adding the municipality"
            )

        for key, value in data.items():
            # To handle the old format
            # Kongeveien 1, Kristiansand
            if "," in address:
                wanted_key = "label"
            else:
                wanted_key = "value"
            if value[wanted_key].lower() == address.lower():
                return value["href"].split("/")[-1]

    return None


async def get_tommeplan_page(street_id, client) -> str:
    """Get the tommeplan page as text"""
    url = (
        f"https://avfallsor.no/henting-av-avfall/finn-hentedag/{street_id.strip('/')}/"
    )
    _LOGGER.debug("Getting the tomme plan page %s", url)
    resp = await client.get(url)
    if resp.status == 200:
        text = await resp.text()
        return text


async def find_address_from_lat_lon(lat, lon, client):
    """Find the adress using lat lon, as a address is required to find the id."""
    if lat is None or lon is None:
        return

    _LOGGER.debug("Trying to find the address using lat %s lon %s", lat, lon)

    url = f"https://ws.geonorge.no/adresser/v1/punktsok?lon={lon}&lat={lat}&radius=20"
    resp = await client.get(url)
    if resp.status == 200:
        result = await resp.json()
        res = result.get("adresser", [])
        if res:
            # The first one seems to be the most correct.
            res = res[0]
            _LOGGER.debug(
                "Got adresse %s from lat %s lon %s", res.get("adressetekst"), lat, lon
            )
            return "%s" % (res["adressetekstutenadressetilleggsnavn"])
    elif resp.status == 400:
        result = await resp.json()
        _LOGGER.info("Api returned 400, error %s", result.get("message", ""))
        raise ValueError("lat and lon is not in Norway.")


async def find_id_from_lat_lon(lat, lon, client):
    """Find the tommeplan if using lat and lon."""
    address = await find_address_from_lat_lon(lat, lon, client)
    return await find_id(address, client)


def parse_tomme_kalender(text):
    final = defaultdict(list)
    soup = BeautifulSoup(text, "html5lib")
    calendar_div = soup.select_one("div.pickup-days-large")

    result = defaultdict(list)
    date = None

    # We need to use a naive approch here as the html structure sucks
    # Avfallsors implementation does not show old pickup dates after todays date and year is missing
    # so we have to do some guess work.
    today = datetime.today()
    for item in calendar_div:
        if item.name == "h3":
            date = item.get_text(strip=True)
            date = parse_date(date)
            # We check if todays date is greater than the date in html, and if it is we will increment the year
            # as old dates are not showed.
            if today > date:
                date = parse_date(item.get_text(strip=True), year=date.year + 1)

        elif item.name == "div":
            classes = []
            span_classes = item.find_all(class_="waste-icon")
            if span_classes:
                for span in span_classes:
                    for s in span["class"]:
                        # Just want to skip this one as it not needed.
                        if s == "waste-icon":
                            continue
                        elif "--" in s:
                            classes.append(s.split("--")[1])
            result[date].extend(classes)

    # The old implementation expects {garbagetype: [datetime.date...]} so we need to make it compatible.
    final = defaultdict(list)
    garbage_types = set(chain.from_iterable(result.values()))

    for trash in garbage_types:
        for key, value in result.items():
            if trash in value:
                final[trash].append(key)

    _LOGGER.debug("%r" % final)

    return final
