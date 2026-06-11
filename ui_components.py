import pygame
import pygame.gfxdraw
import time
import math
from typing import List, Optional, Tuple

import config
from data_models import Aircraft
from airport_data import Airport
import utils


def _aa_circle(surface, colour, center, radius, width=1):
    """Anti-aliased circle outline. Falls back gracefully for radius < 1."""
    x, y, r = int(center[0]), int(center[1]), int(radius)
    if r < 1:
        return
    if width <= 1:
        pygame.gfxdraw.aacircle(surface, x, y, r, colour)
    else:
        for offset in range(width):
            rr = r - offset
            if rr >= 1:
                pygame.gfxdraw.aacircle(surface, x, y, rr, colour)


def _aa_line(surface, colour, p1, p2, width=1):
    """Anti-aliased line. For width > 1 draws parallel lines."""
    if width <= 1:
        pygame.draw.aaline(surface, colour, p1, p2)
    else:
        # Draw a filled rotated rectangle for thick AA lines
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return
        nx = -dy / length * (width / 2)
        ny =  dx / length * (width / 2)
        points = [
            (p1[0] + nx, p1[1] + ny),
            (p2[0] + nx, p2[1] + ny),
            (p2[0] - nx, p2[1] - ny),
            (p1[0] - nx, p1[1] - ny),
        ]
        pygame.gfxdraw.aapolygon(surface, [(int(px), int(py)) for px, py in points], colour)
        pygame.gfxdraw.filled_polygon(surface, [(int(px), int(py)) for px, py in points], colour)


class RadarScope:
    """Radar display component"""
    def __init__(self, screen: pygame.Surface, center_x: int, center_y: int, radius: int):
        self.screen = screen
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.font = utils.load_font(config.RADAR_FONT_SIZE)
        self._bg_surf = None  # pre-rendered static background
        self._build_background()

    def _build_background(self):
        """Pre-render static radar elements (rings, crosshairs) to a surface."""
        size = self.radius * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = self.radius + 2

        # Range rings
        for ring in range(1, 4):
            r = int((ring / 3) * self.radius)
            _aa_circle(surf, config.DIM_GREEN, (cx, cy), r, 1)
            range_nm = int((ring / 3) * config.RADIUS_NM)
            label = self.font.render(f"{range_nm}NM", True, config.DIM_GREEN)
            surf.blit(label, (cx + r - label.get_width() - 2, cy + 4))

        # Crosshairs
        _aa_line(surf, config.DIM_GREEN, (cx - self.radius, cy), (cx + self.radius, cy))
        _aa_line(surf, config.DIM_GREEN, (cx, cy - self.radius), (cx, cy + self.radius))

        # Outer ring (brighter)
        _aa_circle(surf, config.BRIGHT_GREEN, (cx, cy), self.radius, 2)

        self._bg_surf = surf

    def lat_lon_to_screen(self, lat: float, lon: float) -> Optional[Tuple[int, int]]:
        """Convert lat/lon to screen coordinates."""
        lat_km = (lat - config.LAT) * 111
        lon_km = (lon - config.LON) * 111 * math.cos(math.radians(config.LAT))
        range_km = config.RADIUS_NM * 1.852
        x = self.center_x + (lon_km / range_km) * self.radius
        y = self.center_y - (lat_km / range_km) * self.radius
        dx, dy = x - self.center_x, y - self.center_y
        if dx*dx + dy*dy <= self.radius*self.radius:
            return int(x), int(y)
        return None

    def draw_aircraft(self, aircraft: Aircraft, x: int, y: int, colour: tuple):
        """Draw aircraft dot, direction trail, and callsign."""
        dot_r = max(3, int(5 * config.SCALE))
        pygame.gfxdraw.filled_circle(self.screen, x, y, dot_r, colour)
        pygame.gfxdraw.aacircle(self.screen, x, y, dot_r, colour)

        if aircraft.track > 0:
            track_rad = math.radians(aircraft.track)
            trail = config.TRAIL_MIN_LENGTH + (config.TRAIL_MAX_LENGTH - config.TRAIL_MIN_LENGTH) * min(aircraft.speed, config.TRAIL_MAX_SPEED) / config.TRAIL_MAX_SPEED
            tx = x - trail * math.sin(track_rad)
            ty = y + trail * math.cos(track_rad)
            _aa_line(self.screen, colour, (int(tx), int(ty)), (x, y))

        label = self.font.render(aircraft.callsign, True, colour)
        self.screen.blit(label, (x + dot_r + 3, y - label.get_height() // 2))

    def draw_airports(self, airport_list: List[Airport]):
        """Draw airports and runways."""
        AIRPORT_COLOUR = (180, 130, 40)
        RUNWAY_COLOUR  = (220, 180, 60)

        for apt in airport_list:
            pos = self.lat_lon_to_screen(apt.lat, apt.lon)
            if pos is None:
                continue
            ax, ay = pos

            has_visible_runways = False
            if apt.runways:
                for rwy in apt.runways:
                    p1 = self.lat_lon_to_screen(rwy.he_lat, rwy.he_lon)
                    p2 = self.lat_lon_to_screen(rwy.le_lat, rwy.le_lon)
                    if p1 and p2:
                        w = 2 if rwy.width_ft >= 100 else 1
                        _aa_line(self.screen, RUNWAY_COLOUR, p1, p2, w)
                        has_visible_runways = True

            if not has_visible_runways:
                sz = max(3, int(4 * config.SCALE))
                pygame.draw.rect(self.screen, AIRPORT_COLOUR, (ax - sz, ay - sz, sz*2, sz*2), 1)

            # Only label medium/large airports to reduce clutter
            if apt.apt_type in ('large_airport', 'medium_airport'):
                label = self.font.render(apt.ident, True, AIRPORT_COLOUR)
                self.screen.blit(label, (ax + 6, ay - label.get_height() // 2))

    def draw(self, aircraft_list: List[Aircraft], airport_list: List[Airport] = None):
        """Draw the complete radar scope."""
        # Blit pre-rendered background
        bx = self.center_x - self.radius - 2
        by = self.center_y - self.radius - 2
        self.screen.blit(self._bg_surf, (bx, by))

        if airport_list:
            self.draw_airports(airport_list)

        blink_state = int(time.time() * 2) % 2
        for aircraft in aircraft_list:
            pos = self.lat_lon_to_screen(aircraft.lat, aircraft.lon)
            if pos:
                x, y = pos
                if aircraft.is_military:
                    if not config.BLINK_MILITARY or blink_state:
                        self.draw_aircraft(aircraft, x, y, config.RED)
                else:
                    self.draw_aircraft(aircraft, x, y, config.BRIGHT_GREEN)


class DataTable:
    """Aircraft data table component"""
    def __init__(self, screen: pygame.Surface, x: int, y: int, width: int, height: int):
        self.screen = screen
        self.rect = pygame.Rect(x, y, width, height)
        self.font = utils.load_font(config.TABLE_FONT_SIZE)

    def draw(self, aircraft_list: List[Aircraft], status: str, last_update: float):
        """Draw aircraft data table."""
        _aa_line(self.screen, config.BRIGHT_GREEN,
                 self.rect.topleft, self.rect.topright, 2)
        _aa_line(self.screen, config.BRIGHT_GREEN,
                 self.rect.topright, self.rect.bottomright, 2)
        _aa_line(self.screen, config.BRIGHT_GREEN,
                 self.rect.bottomright, self.rect.bottomleft, 2)
        _aa_line(self.screen, config.BRIGHT_GREEN,
                 self.rect.bottomleft, self.rect.topleft, 2)

        title = self.font.render("AIRCRAFT DATA", True, config.AMBER)
        title_rect = title.get_rect(centerx=self.rect.centerx, y=self.rect.y + 10)
        self.screen.blit(title, title_rect)

        headers_y = self.rect.y + 40
        headers = ["CALLSIGN", "   ALT", "SPD", "DIST", "TRK"]
        total_width = self.rect.width - 40
        col_widths = [0.25, 0.25, 0.15, 0.2, 0.15]
        col_positions = []
        current_x = self.rect.x + 20
        for i, width_ratio in enumerate(col_widths):
            w = int(total_width * width_ratio)
            col_positions.append(current_x)
            text = self.font.render(headers[i], True, config.AMBER)
            self.screen.blit(text, (current_x, headers_y))
            current_x += w

        sep_y = headers_y + config.TABLE_FONT_SIZE
        _aa_line(self.screen, config.DIM_GREEN,
                 (self.rect.x + 8, sep_y), (self.rect.right - 8, sep_y))

        sorted_aircraft = sorted(aircraft_list, key=lambda a: a.distance)
        start_y = headers_y + 30
        for i, aircraft in enumerate(sorted_aircraft[:config.MAX_TABLE_ROWS]):
            y_pos = start_y + i * config.TABLE_FONT_SIZE
            colour = config.RED if aircraft.is_military else config.BRIGHT_GREEN
            columns = [
                f"{aircraft.callsign:<8}",
                f"{aircraft.altitude:>6}" if isinstance(aircraft.altitude, int) and aircraft.altitude > 0 else "   N/A",
                f"{aircraft.speed:>3}" if aircraft.speed > 0 else "N/A",
                f"{aircraft.distance:>4.1f}" if aircraft.distance > 0 else "N/A ",
                f"{aircraft.track:>3.0f}°" if aircraft.track > 0 else "N/A"
            ]
            for j, value in enumerate(columns):
                text = self.font.render(str(value), True, colour)
                self.screen.blit(text, (col_positions[j], y_pos))

        military_count = sum(1 for a in aircraft_list if a.is_military)
        elapsed = time.time() - last_update
        countdown = max(0, config.FETCH_INTERVAL - elapsed)
        countdown_text = f"{int(countdown):02d}S" if countdown > 0 else "UPDATING"
        status_info = [
            f"STATUS: {status}",
            f"CONTACTS: {len(aircraft_list)} ({military_count} MIL)",
            f"RANGE: {config.RADIUS_NM}NM",
            f"INTERVAL: {config.FETCH_INTERVAL}S",
            f"NEXT UPDATE: {countdown_text}"
        ]
        status_y = self.rect.bottom - 5 * config.TABLE_FONT_SIZE - 10
        for i, info in enumerate(status_info):
            colour = config.YELLOW if "UPDATING" in info else config.BRIGHT_GREEN
            text = self.font.render(info, True, colour)
            self.screen.blit(text, (self.rect.x + 20, status_y + i * config.TABLE_FONT_SIZE))
