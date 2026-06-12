import configparser
import os

# Configuration Loading
config = configparser.ConfigParser()
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.ini")
config.read(config_path)

# General Settings
FETCH_INTERVAL = config.getint('General', 'FETCH_INTERVAL', fallback=10)
MIL_PREFIX_LIST = [prefix.strip() for prefix in config.get('General', 'MIL_PREFIX_LIST', fallback='7CF').split(',')]
TAR1090_URL = config.get('General', 'TAR1090_URL', fallback='http://localhost/data/aircraft.json')
BLINK_MILITARY = config.getboolean('General', 'BLINK_MILITARY', fallback=True)
SHOW_AIRCRAFT_TRAILS = config.getboolean('General', 'SHOW_AIRCRAFT_TRAILS', fallback=True)
SWEEP_PERIOD = config.getfloat('General', 'SWEEP_PERIOD', fallback=6.0)
USE_INTERNET_FALLBACK = False  # Set to True at runtime when no RTL-SDR is found
# How long (seconds) a contact stays visible after being painted.
# Set to 0 to show contacts only at the moment of sweep.
CONTACT_PERSISTENCE = config.getfloat('General', 'CONTACT_PERSISTENCE', fallback=5.0)

# Audio Settings
ATC_STREAM_URL = config.get('Audio', 'ATC_STREAM_URL', fallback='')
ATC_AUTO_START = config.getboolean('Audio', 'AUTO_START', fallback=False)

# Location Settings
LAT = config.getfloat('Location', 'LAT', fallback=0.0)
LON = config.getfloat('Location', 'LON', fallback=0.0)
AREA_NAME = config.get('Location', 'AREA_NAME', fallback='UNKNOWN')
RADIUS_NM = config.getint('Location', 'RADIUS_NM', fallback=60)

# Display Settings (base values — scaled at runtime by apply_scale())
SCREEN_WIDTH = config.getint('Display', 'SCREEN_WIDTH', fallback=960)
SCREEN_HEIGHT = config.getint('Display', 'SCREEN_HEIGHT', fallback=640)
FPS = config.getint('Display', 'FPS', fallback=6)
MAX_TABLE_ROWS = config.getint('Display', 'MAX_TABLE_ROWS', fallback=10)
FONT_PATH = config.get('Display', 'FONT_PATH', fallback='fonts/TerminusTTF-4.49.3.ttf')
BACKGROUND_PATH = config.get('Display', 'BACKGROUND_PATH', fallback=None)
TRAIL_MIN_LENGTH = config.getint('Display', 'TRAIL_MIN_LENGTH', fallback=8)
TRAIL_MAX_LENGTH = config.getint('Display', 'TRAIL_MAX_LENGTH', fallback=25)
TRAIL_MAX_SPEED = config.getint('Display', 'TRAIL_MAX_SPEED', fallback=500)
HEADER_FONT_SIZE = config.getint('Display', 'HEADER_FONT_SIZE', fallback=32)
RADAR_FONT_SIZE = config.getint('Display', 'RADAR_FONT_SIZE', fallback=28)
TABLE_FONT_SIZE = config.getint('Display', 'TABLE_FONT_SIZE', fallback=28)
INSTRUCTION_FONT_SIZE = config.getint('Display', 'INSTRUCTION_FONT_SIZE', fallback=28)

# Scale factor — updated by apply_scale() before the window is created
SCALE = 1.0

import sys as _sys

def apply_scale(actual_w: int, actual_h: int):
    """Rescale display values to match the actual screen resolution."""
    import importlib
    module = _sys.modules[__name__]

    base_w, base_h = 960, 640
    sx = actual_w / base_w
    sy = actual_h / base_h
    s = min(sx, sy)

    module.SCALE = s
    module.SCREEN_WIDTH = actual_w
    module.SCREEN_HEIGHT = actual_h
    module.TRAIL_MIN_LENGTH  = max(4, int(8  * s))
    module.TRAIL_MAX_LENGTH  = max(8, int(25 * s))
    module.HEADER_FONT_SIZE      = max(14, int(32 * s))
    module.RADAR_FONT_SIZE       = max(12, int(28 * s))
    module.TABLE_FONT_SIZE       = max(12, int(28 * s))
    module.INSTRUCTION_FONT_SIZE = max(12, int(28 * s))

# Colours
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
BRIGHT_GREEN = (50, 255, 50)
DIM_GREEN = (0, 180, 0)
RED = (255, 50, 50)
YELLOW = (255, 255, 0)
AMBER = (255, 191, 0)
