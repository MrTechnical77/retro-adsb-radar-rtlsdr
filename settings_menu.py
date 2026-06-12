"""
Settings overlay — renders over the radar, handles keyboard/touch input,
writes changes to config.ini and applies them live to the config module.
"""
import pygame
import configparser
import os
import math
import config
import utils

# ---------------------------------------------------------------------------
# Schema: (key, label, type)
# type: 'str' | 'float' | 'int' | 'bool' | 'strlist'
# ---------------------------------------------------------------------------
SETTINGS_SCHEMA = [
    ('LOCATION', [
        ('AREA_NAME',  'Area Name',        'str'),
        ('LAT',        'Latitude',         'float'),
        ('LON',        'Longitude',        'float'),
        ('RADIUS_NM',  'Range (NM)',       'int'),
    ]),
    ('RADAR', [
        ('SWEEP_PERIOD',         'Sweep Period (s)',    'float'),
        ('CONTACT_PERSISTENCE',  'Contact Fade (s)',    'float'),
        ('FETCH_INTERVAL',       'Fetch Interval (s)', 'int'),
        ('BLINK_MILITARY',       'Blink Military',     'bool'),
        ('SHOW_AIRCRAFT_TRAILS', 'Aircraft Trails',    'bool'),
        ('MIL_PREFIX_LIST',      'Military Prefixes',  'strlist'),
    ]),
    ('DISPLAY', [
        ('FPS',            'FPS',            'int'),
        ('MAX_TABLE_ROWS', 'Max Table Rows', 'int'),
    ]),
]

# Which config.ini section each key lives in
INI_SECTION = {
    'AREA_NAME':             'Location',
    'LAT':                   'Location',
    'LON':                   'Location',
    'RADIUS_NM':             'Location',
    'SWEEP_PERIOD':          'General',
    'CONTACT_PERSISTENCE':   'General',
    'FETCH_INTERVAL':        'General',
    'BLINK_MILITARY':        'General',
    'SHOW_AIRCRAFT_TRAILS':  'General',
    'MIL_PREFIX_LIST':       'General',
    'FPS':                   'Display',
    'MAX_TABLE_ROWS':        'Display',
}

# Keys that require heavier refresh actions in main.py
NEEDS_AIRPORT_RELOAD  = {'LAT', 'LON', 'RADIUS_NM'}
NEEDS_RADAR_REBUILD   = {'RADIUS_NM'}
NEEDS_SWEEP_UPDATE    = {'SWEEP_PERIOD'}


def _get_current_value(key: str, typ: str) -> str:
    """Read current value from config module as a display string."""
    val = getattr(config, key, '')
    if typ == 'bool':
        return 'true' if val else 'false'
    if typ == 'strlist':
        return ','.join(val) if isinstance(val, list) else str(val)
    return str(val)


def _parse_value(key: str, typ: str, text: str):
    """Parse edited text back to the appropriate Python type."""
    text = text.strip()
    if typ == 'bool':
        return text.lower() in ('true', '1', 'yes')
    if typ == 'int':
        return int(float(text))
    if typ == 'float':
        return float(text)
    if typ == 'strlist':
        return [s.strip() for s in text.split(',') if s.strip()]
    return text


def _apply_to_config(key: str, value):
    """Write a parsed value back to the config module."""
    import sys
    module = sys.modules[config.__name__]
    setattr(module, key, value)


def _write_ini(changes: dict):
    """Persist changes to config.ini on disk."""
    ini = configparser.ConfigParser()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ini_path = os.path.join(script_dir, 'config.ini')
    ini.read(ini_path)
    for key, (typ, value) in changes.items():
        section = INI_SECTION.get(key)
        if section and ini.has_section(section):
            if typ == 'bool':
                ini.set(section, key, 'true' if value else 'false')
            elif typ == 'strlist':
                ini.set(section, key, ','.join(value) if isinstance(value, list) else str(value))
            else:
                ini.set(section, key, str(value))
    with open(ini_path, 'w') as f:
        ini.write(f)


# ---------------------------------------------------------------------------
# SettingsMenu
# ---------------------------------------------------------------------------

class SettingsMenu:
    """Full-screen settings overlay."""

    OVERLAY_ALPHA  = 230
    ROW_PAD        = 6
    SECTION_PAD    = 14
    CURSOR_BLINK   = 0.5   # seconds

    def __init__(self, screen: pygame.Surface):
        self.screen     = screen
        self.is_open    = False
        self.font       = utils.load_font(max(14, int(config.RADAR_FONT_SIZE * 0.9)))
        self.font_bold  = utils.load_font(max(14, int(config.RADAR_FONT_SIZE * 0.9)))
        self.font_small = utils.load_font(max(11, int(config.RADAR_FONT_SIZE * 0.7)))

        self._rows: list    = []   # built on open
        self._active_idx    = None # index into self._rows for the active text field
        self._scroll_offset = 0
        self._cursor_time   = 0.0
        self._error_msg     = ''

        self._save_rect   = None
        self._cancel_rect = None

        # Overlay surface
        self._overlay = pygame.Surface(
            (screen.get_width(), screen.get_height()), pygame.SRCALPHA
        )

    # ------------------------------------------------------------------
    def open(self):
        self.is_open    = True
        self._scroll_offset = 0
        self._active_idx    = None
        self._error_msg     = ''
        self._build_rows()

    def close(self):
        self.is_open     = False
        self._active_idx = None

    # ------------------------------------------------------------------
    def _build_rows(self):
        """Build a flat list of row descriptors from the schema."""
        self._rows = []
        for section_name, fields in SETTINGS_SCHEMA:
            self._rows.append({'kind': 'section', 'label': section_name})
            for key, label, typ in fields:
                self._rows.append({
                    'kind':  'field',
                    'key':   key,
                    'label': label,
                    'typ':   typ,
                    'text':  _get_current_value(key, typ),
                })

    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> dict:
        """
        Process an event. Returns a dict of refresh actions needed:
          {'reload_airports', 'rebuild_radar', 'update_sweep'}
        Returns None if no save happened; returns empty dict on save with no relevant changes.
        Raises 'close' string if user cancelled.
        """
        if not self.is_open:
            return None

        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._handle_click(event.pos)

        # Scroll via mouse wheel
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:
                self._scroll_offset = max(0, self._scroll_offset - 1)
            elif event.button == 5:
                self._scroll_offset += 1

        return None

    def _handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.close()
            return 'close'

        if self._active_idx is None:
            return None

        row = self._rows[self._active_idx]
        if row['kind'] != 'field':
            return None

        if event.key == pygame.K_RETURN:
            self._active_idx = None
        elif event.key == pygame.K_BACKSPACE:
            row['text'] = row['text'][:-1]
        elif event.key == pygame.K_TAB:
            self._advance_active(1 if not (event.mod & pygame.KMOD_SHIFT) else -1)
        elif event.unicode and event.unicode.isprintable():
            row['text'] += event.unicode

        return None

    def _handle_click(self, pos):
        if self._save_rect and self._save_rect.collidepoint(pos):
            return self._save()
        if self._cancel_rect and self._cancel_rect.collidepoint(pos):
            self.close()
            return 'close'

        # Hit-test rows
        for i, (row, rect) in enumerate(self._row_rects):
            if rect and rect.collidepoint(pos):
                if row['kind'] == 'field':
                    if row['typ'] == 'bool':
                        # Toggle
                        row['text'] = 'false' if row['text'] == 'true' else 'true'
                        self._active_idx = None
                    else:
                        self._active_idx = self._rows.index(row)
                break

        return None

    def _advance_active(self, direction):
        if self._active_idx is None:
            return
        idx = self._active_idx + direction
        while 0 <= idx < len(self._rows):
            if self._rows[idx]['kind'] == 'field' and self._rows[idx]['typ'] != 'bool':
                self._active_idx = idx
                return
            idx += direction

    def _save(self):
        changes  = {}
        actions  = set()
        self._error_msg = ''

        for row in self._rows:
            if row['kind'] != 'field':
                continue
            key, typ, text = row['key'], row['typ'], row['text']
            try:
                value = _parse_value(key, typ, text)
            except (ValueError, TypeError):
                self._error_msg = f"Invalid value for {row['label']}"
                return None

            old = getattr(config, key, None)
            if typ == 'strlist':
                old_norm = ','.join(old) if isinstance(old, list) else str(old)
                new_norm = ','.join(value)
                changed  = old_norm != new_norm
            else:
                changed = str(old) != str(value)

            if changed:
                changes[key] = (typ, value)
                if key in NEEDS_AIRPORT_RELOAD:  actions.add('reload_airports')
                if key in NEEDS_RADAR_REBUILD:   actions.add('rebuild_radar')
                if key in NEEDS_SWEEP_UPDATE:    actions.add('update_sweep')

        # Apply all changes
        for key, (typ, value) in changes.items():
            _apply_to_config(key, value)

        if changes:
            _write_ini(changes)

        self.close()
        return actions

    # ------------------------------------------------------------------
    def draw(self, dt: float = 0.016):
        if not self.is_open:
            return

        self._cursor_time += dt
        cursor_on = int(self._cursor_time / self.CURSOR_BLINK) % 2 == 0

        W = self.screen.get_width()
        H = self.screen.get_height()

        # Semi-transparent background
        self._overlay.fill((0, 0, 0, self.OVERLAY_ALPHA))
        self.screen.blit(self._overlay, (0, 0))

        # Panel
        panel_w = min(W - 40, 700)
        panel_h = H - 80
        panel_x = (W - panel_w) // 2
        panel_y = 40
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(self.screen, (0, 0, 0), panel_rect)
        pygame.draw.rect(self.screen, config.BRIGHT_GREEN, panel_rect, 2)

        # Title
        title = self.font_bold.render('⚙ SETTINGS', True, config.AMBER)
        self.screen.blit(title, title.get_rect(centerx=W // 2, y=panel_y + 10))

        # Content area
        content_y_start = panel_y + 44
        content_h       = panel_h - 44 - 50  # leave room for buttons
        row_h = self.font.get_height() + self.ROW_PAD * 2
        col_split = panel_x + panel_w // 2

        # Clipping rect for content
        clip = pygame.Rect(panel_x + 4, content_y_start, panel_w - 8, content_h)
        self.screen.set_clip(clip)

        self._row_rects = []
        y = content_y_start - self._scroll_offset * row_h

        for i, row in enumerate(self._rows):
            if row['kind'] == 'section':
                row_rect = pygame.Rect(panel_x + 8, y, panel_w - 16, row_h)
                if clip.colliderect(row_rect):
                    pygame.draw.line(self.screen, config.DIM_GREEN,
                                     (panel_x + 8, y + row_h - 1),
                                     (panel_x + panel_w - 8, y + row_h - 1))
                    label = self.font_small.render(row['label'], True, config.AMBER)
                    self.screen.blit(label, (panel_x + 8, y + self.ROW_PAD))
                self._row_rects.append((row, None))
                y += row_h

            else:  # field
                row_rect = pygame.Rect(panel_x + 8, y, panel_w - 16, row_h)
                is_active = self._rows.index(row) == self._active_idx

                if clip.colliderect(row_rect):
                    # Highlight active row
                    if is_active:
                        pygame.draw.rect(self.screen, (0, 40, 0), row_rect)

                    # Label
                    lbl_col = config.BRIGHT_GREEN if is_active else config.DIM_GREEN
                    lbl = self.font.render(row['label'], True, lbl_col)
                    self.screen.blit(lbl, (panel_x + 12, y + self.ROW_PAD))

                    # Value
                    if row['typ'] == 'bool':
                        val_text = '[ ON ]' if row['text'] == 'true' else '[OFF]'
                        val_col  = config.BRIGHT_GREEN if row['text'] == 'true' else (180, 60, 60)
                        val_surf = self.font.render(val_text, True, val_col)
                        self.screen.blit(val_surf, (col_split, y + self.ROW_PAD))
                    else:
                        display = row['text']
                        if is_active and cursor_on:
                            display += '|'
                        val_col  = config.BRIGHT_GREEN if is_active else config.DIM_GREEN
                        val_surf = self.font.render(display, True, val_col)
                        # Draw input box
                        box_rect = pygame.Rect(col_split - 4, y + 2,
                                               panel_w - (col_split - panel_x) - 12, row_h - 4)
                        pygame.draw.rect(self.screen, config.DIM_GREEN if is_active else (20, 20, 20), box_rect)
                        pygame.draw.rect(self.screen, config.DIM_GREEN, box_rect, 1)
                        # Clip text to box
                        self.screen.set_clip(box_rect.inflate(-4, -4))
                        self.screen.blit(val_surf, (col_split, y + self.ROW_PAD))
                        self.screen.set_clip(clip)

                    self._row_rects.append((row, row_rect))
                else:
                    self._row_rects.append((row, None))

                y += row_h

        self.screen.set_clip(None)

        # Error message
        if self._error_msg:
            err = self.font_small.render(self._error_msg, True, (255, 80, 80))
            self.screen.blit(err, err.get_rect(centerx=W // 2, y=panel_y + panel_h - 48))

        # Save / Cancel buttons
        btn_w  = max(100, int(120 * config.SCALE))
        btn_h  = max(32, int(38 * config.SCALE))
        btn_y  = panel_y + panel_h - btn_h - 8
        gap    = 20

        self._save_rect   = pygame.Rect(W // 2 - btn_w - gap // 2, btn_y, btn_w, btn_h)
        self._cancel_rect = pygame.Rect(W // 2 + gap // 2,          btn_y, btn_w, btn_h)

        mouse_pos = pygame.mouse.get_pos()
        for rect, label, base_col in (
            (self._save_rect,   'SAVE',   config.BRIGHT_GREEN),
            (self._cancel_rect, 'CANCEL', (180, 60, 60)),
        ):
            hover = rect.collidepoint(mouse_pos)
            col   = base_col if hover else tuple(max(0, c - 80) for c in base_col)
            pygame.draw.rect(self.screen, col, rect, 2)
            surf = self.font.render(label, True, col)
            self.screen.blit(surf, surf.get_rect(center=rect.center))
