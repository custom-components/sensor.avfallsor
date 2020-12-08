import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta

import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


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
    if dates is None:
        return

    today = datetime.now().date()
    for i in sorted(dates):
        if i.date() >= today:
            return i


gb_map = {
    "rest": "Restavfall",
    "bio": "Bioavfall",
    "paper": "Papp, papir og plastemballasje",
    "plastic": "Papp, papir og plastemballasje",
    "metal": "Glass- og metallemballasje",
}
gb_map.update({v: k for k, v in gb_map.items()})


def parse_tomme_kalender(text):
    tomme_days = defaultdict(list)
    # _LOGGER.debug("Used using as soup:\n\n %s", text)
    soup = BeautifulSoup(text, "html5lib")
    today = date.today()
    tomme_days["metal"] = []
    tomme_days["paper"] = []
    tomme_days["rest"] = []
    tomme_days["bio"] = []
    tomme_days["plastic"] = []

    start_of_year = datetime(today.year, 1, 1)
    end_of_year = datetime(today.year, 12, 31)
    tommedag = None

    for c in soup.find_all("form"):
        # Im pretty sure it must be a better way..
        ips = list(c.findAll("input"))
        if len(ips) < 4:
            continue

        avfall_type = [
            i.attrs["value"]
            for i in ips
            if i and i.attrs.get("name", "") == "description"
        ]
        if avfall_type:
            avfall_type = avfall_type[0]

        dato = [
            i.attrs["value"] for i in ips if i and i.attrs.get("name", "") == "dtstart"
        ]
        if dato:
            dato = datetime.strptime(dato[0], "%Y-%m-%d")

        # This should probablybe dropped, we can handle this in the sensor anyway.
        # if tommedag is None and avfall_type == "Restavfall":
        #    tomme_day_nr = dato.weekday()
        #    tomme_days["tomme_day"] = list(nor_days.values())[tomme_day_nr]

        # This is combined in the data, but its splitted in two
        # sensors since it two "bins"
        if gb_map[avfall_type] in ["plastic", "paper"]:
            tomme_days["plastic"].append(dato)
            tomme_days["paper"].append(dato)
        else:
            tomme_days[gb_map[avfall_type]].append(dato)

    # Skip calc for now as there are no exceptions yet.
    # Let just see what the site looks like when after newyears.
    # Maybe download the pdf and parse that if they limit the ammount
    # of pickup days.
    # for i in range(int((end_of_year - start_of_year).days) + 1):
    #
    #    i_date = start_of_year + timedelta(days=i)
    #    if i_date.weekday() == tomme_day_nr:
    #        tomme_days["bio"].append(i_date)
    #        tomme_days["rest"].append(i_date)
    _LOGGER.debug("%s", pprint.pformat(tomme_days, indent=4))

    return tomme_days


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
    if not address:
        return

    # For some silly reason we can't seem to search for anything
    # other then streetname hournumber letter, so we remove the municipality
    # and check that against the label instead.
    if "," in address:
        cleaned_address = address.split(",")[0]
    else:
        cleaned_address = address

    params = {"address": cleaned_address}
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
