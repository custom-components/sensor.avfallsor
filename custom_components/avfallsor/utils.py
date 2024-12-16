import json
import logging
import pprint
from collections import defaultdict
from datetime import date, datetime, timedelta

import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Map Norwegian weekday names to their corresponding indices
weekday_map = {
    "mandager": 0,  # Monday
    "tirsdager": 1,  # Tuesday
    "onsdager": 2,  # Wednesday
    "torsdager": 3,  # Thursday
    "fredager": 4,  # Friday
    "lørdager": 5,  # Saturday
    "søndager": 6   # Sunday
}

def get_next_weekdaydate(weekday_name):

    # Convert the input string to a weekday index
    weekday_index = weekday_map.get(weekday_name.lower())

    if weekday_index is None:
        raise ValueError(f"Invalid weekday name: {weekday_name}")

    # Get today's date and weekday
    today = datetime.today()
    current_weekday = today.weekday()

    # Calculate the number of days until the next desired weekday
    days_ahead = (weekday_index - current_weekday + 7) % 7
    # If the desired day is today, set to the next occurrence (7 days ahead)
    days_ahead = 7 if days_ahead == 0 else days_ahead

    # Calculate the next occurrence of the desired weekday
    next_weekday_date = today + timedelta(days=days_ahead)
    return next_weekday_date

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
    "paper": "Papir/papp",
    "plastic": "Papir/papp",
    "metal": "Glass- og metallemballasje",
}
gb_map.update({v: k for k, v in gb_map.items()})


def parse_tomme_kalender(text):
    tomme_days = defaultdict(list)
    # _LOGGER.debug("Used using as soup:\n\n %s", text)
    #soup = BeautifulSoup(text, "html5lib")

    soup = BeautifulSoup(text, "html.parser")


    forms = soup.find_all("form", class_="info-boxes-box-form")

    # Create a dictionary to store the description and dtstart values
    neste_hentedager = {}


    # Metall, papp- og papir and plast dates are all found inside a form elements
    for form in forms:
        description_input = form.find("input", {"name": "description"})
        dtstart_input = form.find("input", {"name": "dtstart"})
        
        if description_input and dtstart_input:
            description = description_input.get("value")
            dtstart = dtstart_input.get("value")
            neste_hentedager[description] = datetime.strptime(dtstart, "%Y-%m-%d")

    additional_waste_classes = {
        "Restavfall": "info-boxes-box info-boxes-box--9011",
        "Matavfall": "info-boxes-box info-boxes-box--1111"
    }

    for waste_type, waste_class in additional_waste_classes.items():
        div = soup.find("div", class_=waste_class)
        if div:
            spans = div.find_all("span")  # Find all <span> elements within the div
            for span in spans:
                text = span.get_text()  # Get the text of each <span>
                # Check if any weekday is in the text
                for weekday in weekday_map:
                    if weekday in text:
                        neste_hentedager[waste_type] = get_next_weekdaydate(weekday).replace(hour=0, minute=0, second=0, microsecond=0)
                        break
        else:
            print("Div not found")

    tomme_days = {
        "metal" : [neste_hentedager["Glass- og metallemballasje"]],
        "paper" : [neste_hentedager["Papp og papir"]],
        "rest" : [neste_hentedager["Restavfall"]],
        "bio" : [neste_hentedager["Matavfall"]],
        "plastic" : [neste_hentedager["Plastemballasje"]]
    }

    _LOGGER.debug(tomme_days)

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
