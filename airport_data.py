"""
Downloads and caches OurAirports data, filters airports/runways within radar range.
Data is cached to disk after first download.
"""
import os
import csv
import math
import urllib.request
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

import config

CACHE_DIR = os.path.expanduser("~/.cache/retro-adsb-radar")
AIRPORTS_CSV = os.path.join(CACHE_DIR, "airports.csv")
RUNWAYS_CSV  = os.path.join(CACHE_DIR, "runways.csv")

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL  = "https://davidmegginson.github.io/ourairports-data/runways.csv"

SHOW_TYPES = {"large_airport", "medium_airport", "small_airport"}


@dataclass
class Runway:
    """A single runway with two endpoints."""
    he_lat: float
    he_lon: float
    le_lat: float
    le_lon: float
    width_ft: int = 0


@dataclass
class Airport:
    """An airport within radar range."""
    ident: str        # ICAO/local code shown on radar
    name: str
    lat: float
    lon: float
    apt_type: str
    runways: List[Runway] = field(default_factory=list)


def _haversine_nm(lat1, lon1, lat2, lon2) -> float:
    R = 3440.065  # Earth radius in nautical miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _download(url: str, dest: str):
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    print(f"Saved to {dest}")


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(AIRPORTS_CSV):
        _download(AIRPORTS_URL, AIRPORTS_CSV)
    if not os.path.exists(RUNWAYS_CSV):
        _download(RUNWAYS_URL, RUNWAYS_CSV)


def load_airports() -> List[Airport]:
    """Load and return airports within the configured radar range."""
    _ensure_cache()

    # Load airports
    airports: dict[str, Airport] = {}
    with open(AIRPORTS_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('type') not in SHOW_TYPES:
                continue
            try:
                lat = float(row['latitude_deg'])
                lon = float(row['longitude_deg'])
            except (ValueError, KeyError):
                continue
            dist = _haversine_nm(config.LAT, config.LON, lat, lon)
            if dist > config.RADIUS_NM:
                continue
            ident = row.get('gps_code') or row.get('ident') or row.get('local_code') or '???'
            airports[row['ident']] = Airport(
                ident=ident,
                name=row.get('name', ''),
                lat=lat,
                lon=lon,
                apt_type=row['type'],
            )

    # Attach runways
    with open(RUNWAYS_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            apt_ident = row.get('airport_ident', '')
            if apt_ident not in airports:
                continue
            try:
                he_lat = float(row['he_latitude_deg'])
                he_lon = float(row['he_longitude_deg'])
                le_lat = float(row['le_latitude_deg'])
                le_lon = float(row['le_longitude_deg'])
                width  = int(float(row.get('width_ft') or 0))
            except (ValueError, TypeError):
                continue
            airports[apt_ident].runways.append(Runway(he_lat, he_lon, le_lat, le_lon, width))

    result = list(airports.values())
    print(f"Loaded {len(result)} airports within {config.RADIUS_NM}NM")
    return result
