import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import nor_days, nor_months

_LOGGER = logging.getLogger(__name__)


def check_settings(config, hass):
    if not any(config.get(i) for i in ["street_id", "municipality"]):
        _LOGGER.debug("street_id or municipality was not set config")
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


def to_dt(s):
    # if a year is missing we assume it is this year.
    # this seems to only be a issue with the tomme exceptions.
    if not re.search(r"\d{4}", s):
        s = "%s %s" % (s, date.today().year)

    s = s.capitalize()

    for key, value in nor_days.items():
        if key.lower() in s.lower():
            s = s.replace(key, value)

    for k, v in nor_months.items():
        if k.lower() in s.lower():
            s = s.replace(k, v)

    return datetime.strptime(s.strip(), "%A %d. %b %Y")


def longestSubstring(str1, str2):
    """Not in use atm"""
    seqMatch = SequenceMatcher(None, str1, str2)
    match = seqMatch.find_longest_match(0, len(str1), 0, len(str2))
    return match.size


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
    soup = BeautifulSoup(text, "html.parser")
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
        if tommedag is None and avfall_type == "Restavfall":
            tomme_day_nr = dato.weekday()
            tomme_days["tomme_day"] = list(nor_days.values())[tomme_day_nr]


        # This is combined in the data, but its splitted in two
        # sensors since it two "bins"
        if gb_map[avfall_type] in ["plastic", "paper"]:
            tomme_days["plastic"].append(dato)
            tomme_days["paper"].append(dato)
        else:
            tomme_days[gb_map[avfall_type]].append(dato)

    # Skip calc for now as there are no exceptions yet.
    # for i in range(int((end_of_year - start_of_year).days) + 1):
    #
    #    i_date = start_of_year + timedelta(days=i)
    #    if i_date.weekday() == tomme_day_nr:
    #        tomme_days["bio"].append(i_date)
    #        tomme_days["rest"].append(i_date)

    return tomme_days


def parse_tomme_kalender_old(text):
    """Parse the avfallsør tømme kalender to a dict."""


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
        if hasattr(li, "img"):
            if "grønn" in li.img.get("alt", ""):
                tomme_days["paper"].append(to_dt(li.text.strip()))
                tomme_days["plastic"].append(to_dt(li.text.strip()))
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
                    elif "Grønn" in item["src"]:
                        exceptions["paper"].append((to_dt(old), to_dt(new)))
                        exceptions["plastic"].append((to_dt(old), to_dt(new)))
                    elif "glass" in item["src"]:
                        exceptions["metal"].append((to_dt(old), to_dt(new)))

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
    if len(exceptions):
        for k, v in exceptions.items():
            for i in v:
                for item in tomme_days.get(k, []):
                    if i and i[0] == item:
                        tomme_days[k].remove(item)
                        tomme_days[k].append(i[1])

    return tomme_days


async def verify_that_we_can_find_adr(config, hass):
    client = async_get_clientsession(hass)
    try:
        adr = await find_id(config.get("address"), client)
        if adr:
            return True
    except:
        pass

    try:
        adr = await find_id_from_lat_lon(
            hass.config.latitude, hass.config.longitude, client
        )
        if adr:
            return True
    except:
        pass

    try:
        # This just to check the lat and lon, the other
        # stuff is tested above.
        chk = check_settings(config, hass)
        if chk:
            return True
    except vol.Invalid:
        return False

    return False


async def find_id(address, client):
    """Find the id that avfall sør uses to create the tømmeplan"""
    if not address:
        return

    d = {"address": address}
    url = "https://avfallsor.no/wp-json/addresses/v1/address"
    resp = await client.get(url, params=d)

    if resp.status == 200:
        data = await resp.json()

        if len(data) > 1:
            _LOGGER.warning(
                "We got multiple adresses, consider extracting the id manually."
            )

        for key, value in data.items():
            if value["value"].lower() == address.lower():
                return value["href"].split("/")[-1]


async def find_address(address, client):
    """not in use anymore"""
    if not address:
        return

    d = {"searchstring": address}
    url = "https://seeiendom.kartverket.no/api/soekEtterEiendom"
    resp = await client.get(url, params=d)

    if resp.status == 200:
        result = await resp.json()
        if len(result):
            res = result[0]
            _LOGGER.debug("Got %s", res["veiadresse"])
            res = "%s" % res["veiadresse"].split(",")[0]
            return res
        else:
            _LOGGER.info("Failed to find the address %s", address)


async def find_address_from_lat_lon(lat, lon, client):
    if lat is None or lon is None:
        return

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
            # return '%s.%s.%s.%s' % (res["kommunenummer"], res["gardsnummer"], res["bruksnummer"], res["festenummer"])
            return "%s" % (
                res["adressetekstutenadressetilleggsnavn"]
            )
    elif resp.status == 400:
        result = await resp.json()
        _LOGGER.info("Api returned 400, error %r", result.get("message", ""))
        raise ValueError("lat and lon is not in Norway.")


async def find_id_from_lat_lon(lat, lon, client):
    adress = await find_address_from_lat_lon(lat, lon, client)
    return await find_id(adress, client)
