"""
Simulated aircraft tracker for demo mode.
Generates fake moving aircraft around the configured centre point — no RTL-SDR needed.
"""
import math
import time
import threading
from typing import List
from dataclasses import dataclass

import config
from data_models import Aircraft
from utils import calculate_distance_bearing


def _offset_lat_lon(lat, lon, bearing_deg, distance_nm):
    """Return a lat/lon that is `distance_nm` away from lat/lon at `bearing_deg`."""
    R = 3440.065  # Earth radius in NM
    d = distance_nm / R
    b = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                     math.cos(lat1) * math.sin(d) * math.cos(b))
    lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


# Seeded aircraft: (callsign, bearing, dist_nm, altitude_ft, speed_kts, is_military)
_SEED = [
    ('AAL123',   25,  12, 35000, 480, False),
    ('UAL456',   80,  28, 28500, 445, False),
    ('DAL789',  140,  38, 32000, 510, False),
    ('SWA101',  195,  18, 18500, 375, False),
    ('FDX202',  250,  32, 24000, 430, False),
    ('UPS303',  305,  10, 14500, 320, False),
    ('N8472P',   55,   7,  5500, 145, False),
    ('C17A001', 165,  42, 29000, 495, True),   # military
    ('SKW3341', 330,  22, 22000, 400, False),
    ('N2291K',  100,  15,  3500, 110, False),
]


class DemoAircraftTracker:
    """Mimics AircraftTracker but returns generated fake aircraft."""

    def __init__(self):
        self.aircraft: List[Aircraft] = []
        self.status      = 'DEMO'
        self.last_update = time.time()
        self.running     = True
        self._positions  = []   # mutable lat/lon for each seed aircraft
        self._init_positions()

    def _init_positions(self):
        self._positions = []
        for _, bearing, dist, _, _, _ in _SEED:
            lat, lon = _offset_lat_lon(config.LAT, config.LON, bearing, dist)
            self._positions.append([lat, lon])

    def _move(self):
        """Nudge each aircraft along its track by speed * elapsed."""
        dt_hours = config.FETCH_INTERVAL / 3600.0
        for i, (_, bearing, _, _, speed, _) in enumerate(_SEED):
            dist_nm = speed * dt_hours
            lat, lon = _offset_lat_lon(
                self._positions[i][0], self._positions[i][1],
                bearing, dist_nm
            )
            self._positions[i] = [lat, lon]

    def _build_aircraft(self) -> List[Aircraft]:
        result = []
        for i, (callsign, bearing, _, alt, speed, mil) in enumerate(_SEED):
            lat, lon = self._positions[i]
            dist, brg = calculate_distance_bearing(config.LAT, config.LON, lat, lon)
            if dist > config.RADIUS_NM:
                continue
            result.append(Aircraft(
                hex_code    = f'demo{i:02x}',
                callsign    = callsign,
                lat         = lat,
                lon         = lon,
                altitude    = alt,
                speed       = speed,
                track       = float(bearing),
                distance    = dist,
                bearing     = brg,
                is_military = mil,
            ))
        return result

    def _loop(self):
        while self.running:
            self._move()
            self.aircraft    = self._build_aircraft()
            self.status      = 'DEMO'
            self.last_update = time.time()
            time.sleep(config.FETCH_INTERVAL)

    def start(self):
        self.aircraft = self._build_aircraft()
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
