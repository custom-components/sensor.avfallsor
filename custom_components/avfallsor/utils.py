import logging
import re

from difflib import SequenceMatcher
from collections import defaultdict

from datetime import datetime, date, timedelta

from . import nor_days, nor_months


_LOGGER = logging.getLogger(__name__)


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


def longestSubstring(str1, str2):
    """Not in use atm"""
    seqMatch = SequenceMatcher(None, str1, str2)
    match = seqMatch.find_longest_match(0, len(str1), 0, len(str2))
    return match.size


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
                elif "Grønn" in item["src"]:
                    exceptions["paper"].append((to_dt(old), to_dt(new)))
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


async def find_address(address, client):
    if not address:
        return

    d = {"searchstring": address}
    url = "https://seeiendom.kartverket.no/api/soekEtterEiendom"
    resp = await client.get(url, params=d)

    if resp.status == 200:
        result = await resp.json()
        if len(result):
            res = result[0]
            _LOGGER.info('Got %s', res["veiadresse"])
            res = '%s.%s.%s.%s' % (res["kommunenr"], res["gaardsnr"], res["bruksnr"], res["festenr"])
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
            _LOGGER.info('Got adresse %s from lat %s lon %s', res.get("adressetekst"), lat, lon)
            return '%s.%s.%s.%s' % (res["kommunenummer"], res["gardsnummer"], res["bruksnummer"], res["festenummer"])
    elif resp.status == 400:
        result = await resp.json()
        _LOGGER.info("Api returned 400, error %r", result.get("message", ""))
        raise ValueError('lat and lon is not in Norway.')
