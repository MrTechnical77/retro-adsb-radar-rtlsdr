import pygame
import pygame.gfxdraw
import time
import math
from typing import List, Optional, Tuple, Dict

import config
from data_models import Aircraft
from airport_data import Airport
import utils


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _aa_circle(surface, colour, center, radius, width=1):
    x, y, r = int(center[0]), int(center[1]), int(radius)
    if r < 1:
        return
    for offset in range(max(1, width)):
        rr = r - offset
        if rr >= 1:
            pygame.gfxdraw.aacircle(surface, x, y, rr, colour)


def _aa_line(surface, colour, p1, p2, width=1):
    if width <= 1:
        pygame.draw.aaline(surface, colour, p1, p2)
    else:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return
        nx = -dy / length * (width / 2)
        ny =  dx / length * (width / 2)
        pts = [
            (int(p1[0] + nx), int(p1[1] + ny)),
            (int(p2[0] + nx), int(p2[1] + ny)),
            (int(p2[0] - nx), int(p2[1] - ny)),
            (int(p1[0] - nx), int(p1[1] - ny)),
        ]
        pygame.gfxdraw.aapolygon(surface, pts, colour)
        pygame.gfxdraw.filled_polygon(surface, pts, colour)


def _lerp_colour(a, b, t):
    """Linearly interpolate between two RGB colours."""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------------------------------------------------------------------------
# Radar scope
# ---------------------------------------------------------------------------

DIM_AIRCRAFT = (0, 55, 0)
DIM_MILITARY = (60, 0, 0)

ZOOM_STEPS = [10, 20, 30, 50, 75, 100, 150, 200, 300]


class RadarScope:
    """Radar display with animated sweep and painted aircraft contacts."""

    def __init__(self, screen: pygame.Surface, center_x: int, center_y: int, radius: int):
        self.screen    = screen
        self.center_x  = center_x
        self.center_y  = center_y
        self.radius    = radius
        self.font      = utils.load_font(config.RADAR_FONT_SIZE)

        self.sweep_angle = 0.0
        self.sweep_speed = 360.0 / config.SWEEP_PERIOD
        self._last_time  = time.time()

        self._painted: Dict[str, dict] = {}

        # Zoom button rects — set during draw(), used for hit testing
        self._btn_minus: Optional[pygame.Rect] = None
        self._btn_plus:  Optional[pygame.Rect] = None

        self._bg_surf = None
        self._build_background()

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    @property
    def painted_aircraft(self) -> List[Aircraft]:
        """Aircraft currently visible on radar (last painted snapshot)."""
        return [p['aircraft'] for p in self._painted.values()]

    def _zoom_index(self) -> int:
        """Return the index in ZOOM_STEPS closest to current RADIUS_NM."""
        return min(range(len(ZOOM_STEPS)),
                   key=lambda i: abs(ZOOM_STEPS[i] - config.RADIUS_NM))

    def zoom_in(self) -> bool:
        idx = self._zoom_index()
        if idx > 0:
            config.RADIUS_NM = ZOOM_STEPS[idx - 1]
            self._painted.clear()
            self._build_background()
            return True
        return False

    def zoom_out(self) -> bool:
        idx = self._zoom_index()
        if idx < len(ZOOM_STEPS) - 1:
            config.RADIUS_NM = ZOOM_STEPS[idx + 1]
            self._painted.clear()
            self._build_background()
            return True
        return False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle click/scroll events. Returns True if zoom changed."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self._btn_minus and self._btn_minus.collidepoint(event.pos):
                    return self.zoom_in()
                if self._btn_plus and self._btn_plus.collidepoint(event.pos):
                    return self.zoom_out()
            elif event.button == 4:   # scroll up = zoom in
                return self.zoom_in()
            elif event.button == 5:   # scroll down = zoom out
                return self.zoom_out()
        return False

    # ------------------------------------------------------------------
    # Static background (rings + crosshairs) — built once
    # ------------------------------------------------------------------

    def _build_background(self):
        size = self.radius * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = self.radius + 2

        for ring in range(1, 4):
            r = int((ring / 3) * self.radius)
            _aa_circle(surf, config.DIM_GREEN, (cx, cy), r, 1)
            range_nm = int((ring / 3) * config.RADIUS_NM)
            label = self.font.render(f"{range_nm}NM", True, config.DIM_GREEN)
            surf.blit(label, (cx + r - label.get_width() - 2, cy + 4))

        _aa_line(surf, config.DIM_GREEN, (cx - self.radius, cy), (cx + self.radius, cy))
        _aa_line(surf, config.DIM_GREEN, (cx, cy - self.radius), (cx, cy + self.radius))
        _aa_circle(surf, config.BRIGHT_GREEN, (cx, cy), self.radius, 2)

        self._bg_surf = surf

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def lat_lon_to_screen(self, lat: float, lon: float) -> Optional[Tuple[int, int]]:
        lat_km  = (lat - config.LAT) * 111
        lon_km  = (lon - config.LON) * 111 * math.cos(math.radians(config.LAT))
        range_km = config.RADIUS_NM * 1.852
        x = self.center_x + (lon_km / range_km) * self.radius
        y = self.center_y - (lat_km / range_km) * self.radius
        dx, dy = x - self.center_x, y - self.center_y
        if dx*dx + dy*dy <= self.radius*self.radius:
            return int(x), int(y)
        return None

    # ------------------------------------------------------------------
    # Sweep mechanics
    # ------------------------------------------------------------------

    def _advance_sweep(self) -> float:
        """Advance sweep angle, return previous angle."""
        now = time.time()
        dt  = now - self._last_time
        self._last_time = now
        prev = self.sweep_angle
        self.sweep_angle = (self.sweep_angle + self.sweep_speed * dt) % 360.0
        return prev

    def _sweep_passes(self, bearing: float, prev: float, curr: float) -> bool:
        """True if the sweep crossed `bearing` going from prev to curr (clockwise)."""
        b = bearing % 360
        if prev <= curr:
            return prev <= b < curr
        else:  # wrapped through 0
            return b >= prev or b < curr

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_sweep(self):
        cx, cy, r = self.center_x, self.center_y, self.radius
        angle_rad = math.radians(self.sweep_angle - 90)
        ex = int(cx + r * math.cos(angle_rad))
        ey = int(cy + r * math.sin(angle_rad))
        pygame.draw.aaline(self.screen, config.BRIGHT_GREEN, (cx, cy), (ex, ey))

    def draw_aircraft(self, aircraft: Aircraft, x: int, y: int, colour: tuple):
        dot_r = max(3, int(5 * config.SCALE))
        pygame.gfxdraw.filled_circle(self.screen, x, y, dot_r, colour)
        pygame.gfxdraw.aacircle(self.screen, x, y, dot_r, colour)

        if config.SHOW_AIRCRAFT_TRAILS and aircraft.track > 0:
            track_rad = math.radians(aircraft.track)
            trail = (config.TRAIL_MIN_LENGTH +
                     (config.TRAIL_MAX_LENGTH - config.TRAIL_MIN_LENGTH) *
                     min(aircraft.speed, config.TRAIL_MAX_SPEED) / config.TRAIL_MAX_SPEED)
            tx = x - trail * math.sin(track_rad)
            ty = y + trail * math.cos(track_rad)
            _aa_line(self.screen, colour, (int(tx), int(ty)), (x, y))

        if config.RADIUS_NM <= 50 or aircraft.is_military:
            label = self.font.render(aircraft.callsign, True, colour)
            self.screen.blit(label, (x + dot_r + 3, y - label.get_height() // 2))

    def draw_airports(self, airport_list: List[Airport]):
        AIRPORT_COL = (180, 130, 40)
        RUNWAY_COL  = (220, 180, 60)

        labelled_only = config.RADIUS_NM > 30

        for apt in airport_list:
            if labelled_only and apt.apt_type not in ('large_airport', 'medium_airport'):
                continue

            pos = self.lat_lon_to_screen(apt.lat, apt.lon)
            if pos is None:
                continue
            ax, ay = pos
            has_runways = False

            for rwy in apt.runways:
                p1 = self.lat_lon_to_screen(rwy.he_lat, rwy.he_lon)
                p2 = self.lat_lon_to_screen(rwy.le_lat, rwy.le_lon)
                if p1 and p2:
                    w = 2 if rwy.width_ft >= 100 else 1
                    _aa_line(self.screen, RUNWAY_COL, p1, p2, w)
                    has_runways = True

            if not has_runways:
                sz = max(3, int(4 * config.SCALE))
                pygame.draw.rect(self.screen, AIRPORT_COL, (ax - sz, ay - sz, sz*2, sz*2), 1)

            if apt.apt_type in ('large_airport', 'medium_airport'):
                label = self.font.render(apt.ident, True, AIRPORT_COL)
                self.screen.blit(label, (ax + 6, ay - label.get_height() // 2))

    def _draw_zoom_buttons(self):
        """Draw [-] RANGE [+] buttons below the radar scope."""
        mouse_pos = pygame.mouse.get_pos()
        btn_size  = max(28, int(32 * config.SCALE))
        gap       = max(6,  int(8  * config.SCALE))
        y         = self.center_y + self.radius + gap

        label     = self.font.render(f"{config.RADIUS_NM}NM", True, config.AMBER)
        lw        = label.get_width()
        total_w   = btn_size + gap + lw + gap + btn_size
        x_start   = self.center_x - total_w // 2

        self._btn_minus = pygame.Rect(x_start, y, btn_size, btn_size)
        self._btn_plus  = pygame.Rect(x_start + btn_size + gap + lw + gap, y, btn_size, btn_size)

        for btn, symbol in ((self._btn_minus, "-"), (self._btn_plus, "+")):
            hover  = btn.collidepoint(mouse_pos)
            colour = config.BRIGHT_GREEN if hover else config.DIM_GREEN
            pygame.draw.rect(self.screen, colour, btn, 1)
            sym    = self.font.render(symbol, True, colour)
            self.screen.blit(sym, sym.get_rect(center=btn.center))

        self.screen.blit(label, (x_start + btn_size + gap, y + (btn_size - label.get_height()) // 2))

    def draw(self, aircraft_list: List[Aircraft], airport_list: List[Airport] = None):
        # 1. Static background
        bx = self.center_x - self.radius - 2
        by = self.center_y - self.radius - 2
        self.screen.blit(self._bg_surf, (bx, by))

        # 2. Airports (static, drawn before sweep)
        if airport_list:
            self.draw_airports(airport_list)

        # 3. Advance sweep and paint aircraft that the line crosses
        prev_angle = self.sweep_angle
        prev_angle = self._advance_sweep()  # returns previous; self.sweep_angle is now new

        active_hexes = {ac.hex_code for ac in aircraft_list}
        for ac in aircraft_list:
            if self._sweep_passes(ac.bearing, prev_angle, self.sweep_angle):
                pos = self.lat_lon_to_screen(ac.lat, ac.lon)
                if pos:
                    self._painted[ac.hex_code] = {
                        'x': pos[0], 'y': pos[1],
                        'aircraft': ac,
                        'time': time.time(),
                    }

        # Remove contacts that are no longer in the live feed
        self._painted = {k: v for k, v in self._painted.items() if k in active_hexes}

        # 4. Draw fading painted contacts
        now = time.time()
        blink_state = int(time.time() * 2) % 2
        for paint in self._painted.values():
            age = now - paint['time']
            persistence = config.CONTACT_PERSISTENCE
            if persistence <= 0:
                t = 1.0 if age < 0.1 else 0.0
            else:
                hold = persistence * 0.15
                if age < hold:
                    t = 1.0
                else:
                    t = max(0.0, 1.0 - (age - hold) / (persistence * 0.85))

            ac = paint['aircraft']
            if ac.is_military:
                if not config.BLINK_MILITARY or blink_state:
                    colour = _lerp_colour(DIM_MILITARY, config.RED, t)
                    self.draw_aircraft(ac, paint['x'], paint['y'], colour)
            else:
                colour = _lerp_colour(DIM_AIRCRAFT, config.BRIGHT_GREEN, t)
                self.draw_aircraft(ac, paint['x'], paint['y'], colour)

        # 5. Zoom buttons
        self._draw_zoom_buttons()

        # 6. Sweep line on top of everything
        self._draw_sweep()


# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------

class DataTable:
    """Aircraft data table component"""
    def __init__(self, screen: pygame.Surface, x: int, y: int, width: int, height: int):
        self.screen = screen
        self.rect   = pygame.Rect(x, y, width, height)
        self.font   = utils.load_font(config.TABLE_FONT_SIZE)

    def draw(self, aircraft_list: List[Aircraft], status: str, last_update: float):
        # Border
        for p1, p2 in [
            (self.rect.topleft,    self.rect.topright),
            (self.rect.topright,   self.rect.bottomright),
            (self.rect.bottomright,self.rect.bottomleft),
            (self.rect.bottomleft, self.rect.topleft),
        ]:
            _aa_line(self.screen, config.BRIGHT_GREEN, p1, p2, 2)

        title = self.font.render("AIRCRAFT DATA", True, config.AMBER)
        self.screen.blit(title, title.get_rect(centerx=self.rect.centerx, y=self.rect.y + 10))

        headers_y = self.rect.y + 40
        headers    = ["CALLSIGN", "   ALT", "SPD", "DIST", "TRK"]
        col_ratios = [0.25, 0.25, 0.15, 0.2, 0.15]
        total_w    = self.rect.width - 40
        col_x      = []
        cx         = self.rect.x + 20
        for ratio, header in zip(col_ratios, headers):
            col_x.append(cx)
            self.screen.blit(self.font.render(header, True, config.AMBER), (cx, headers_y))
            cx += int(total_w * ratio)

        _aa_line(self.screen, config.DIM_GREEN,
                 (self.rect.x + 8, headers_y + config.TABLE_FONT_SIZE),
                 (self.rect.right - 8, headers_y + config.TABLE_FONT_SIZE))

        sorted_ac = sorted(aircraft_list, key=lambda a: a.distance)
        row_y = headers_y + 30
        for i, ac in enumerate(sorted_ac[:config.MAX_TABLE_ROWS]):
            y_pos  = row_y + i * config.TABLE_FONT_SIZE
            colour = config.RED if ac.is_military else config.BRIGHT_GREEN
            cols   = [
                f"{ac.callsign:<8}",
                f"{ac.altitude:>6}" if isinstance(ac.altitude, int) and ac.altitude > 0 else "   N/A",
                f"{ac.speed:>3}"    if ac.speed > 0    else "N/A",
                f"{ac.distance:>4.1f}" if ac.distance > 0 else "N/A ",
                f"{ac.track:>3.0f}°"  if ac.track > 0   else "N/A",
            ]
            for j, val in enumerate(cols):
                self.screen.blit(self.font.render(val, True, colour), (col_x[j], y_pos))

        mil_count = sum(1 for a in aircraft_list if a.is_military)
        elapsed   = time.time() - last_update
        countdown = max(0, config.FETCH_INTERVAL - elapsed)
        cd_text   = f"{int(countdown):02d}S" if countdown > 0 else "UPDATING"
        status_lines = [
            f"STATUS: {status}",
            f"CONTACTS: {len(aircraft_list)} ({mil_count} MIL)",
            f"RANGE: {config.RADIUS_NM}NM",
            f"INTERVAL: {config.FETCH_INTERVAL}S",
            f"NEXT UPDATE: {cd_text}",
        ]
        sy = self.rect.bottom - 5 * config.TABLE_FONT_SIZE - 10
        for i, line in enumerate(status_lines):
            colour = config.YELLOW if "UPDATING" in line else config.BRIGHT_GREEN
            self.screen.blit(self.font.render(line, True, colour),
                             (self.rect.x + 20, sy + i * config.TABLE_FONT_SIZE))
