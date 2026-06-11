# Retro ADS-B Radar ✈

Aircraft radar display built with Python and Pygame. Visualises real-time aircraft positions and metadata from a local RTL-SDR dongle, with a retro interface.

This is a fork of [nicespoon/retro-adsb-radar](https://github.com/nicespoon/retro-adsb-radar) with the following additions:

- **dump1090 auto-start** — no separate ADS-B decoder setup required; the app launches and manages dump1090 automatically
- **Animated radar sweep** — rotating sweep line with aircraft contacts that paint and fade like real radar
- **Airport overlay** — airports within radar range drawn on the scope with runway shapes
- **In-app zoom control** — tap `[-]` / `[+]` buttons on the radar to change range without editing config
- **Auto-scaling display** — adapts to any screen resolution automatically
- **Anti-aliased rendering** — smooth circles and lines via pygame.gfxdraw

![Retro ADS-B Radar Screenshot](images/screenshot.png)

## Hardware Requirements

- Raspberry Pi (Pi 4 or Pi 5 recommended)
- [RTL-SDR Blog V4](https://www.rtl-sdr.com/rtl-sdr-blog-v-4-dongle-initial-release/) or similar RTL-SDR dongle
- 1090 MHz antenna
- Display (works well on the official Raspberry Pi 7" touchscreen)

## Quick Start

### 1. Install the RTL-SDR Blog driver

The standard `librtlsdr` package does not fully support the V4 dongle. Install the RTL-SDR Blog driver instead:

```bash
sudo apt remove librtlsdr-dev rtl-sdr
git clone https://github.com/rtlsdrblog/rtl-sdr-blog.git
cd rtl-sdr-blog && mkdir build && cd build
cmake .. -DINSTALL_UDEV_RULES=ON
make -j4 && sudo make install && sudo ldconfig
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
```

### 2. Build dump1090

```bash
sudo apt install -y libncurses-dev
git clone https://github.com/flightaware/dump1090.git
cd dump1090 && make -j4
```

### 3. Clone and set up the radar

```bash
git clone https://github.com/MrTechnical77/retro-adsb-radar-rtlsdr.git
cd retro-adsb-radar-rtlsdr
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.ini.example config.ini
nano config.ini
```

Set your latitude, longitude, and area name in `config.ini`, then run:

```bash
python3 main.py
```

The app will automatically start dump1090, wait for it to initialise, then launch the radar UI. Closing the app also stops dump1090.

### 4. Optional: launch from the desktop

```bash
chmod +x launch.sh
cp retro-adsb-radar.desktop ~/.local/share/applications/
```

The app will appear in the Raspberry Pi start menu under Accessories.

## Configuration

All settings live in `config.ini`.

```ini
[General]
FETCH_INTERVAL = 10           # How often to poll dump1090 for new data (seconds)
MIL_PREFIX_LIST = 7CF         # Comma-separated ICAO hex prefixes to flag as military
TAR1090_URL = http://localhost:8080/aircraft.json  # dump1090 JSON endpoint (don't change)
BLINK_MILITARY = true         # Blink military contacts on sweep
SHOW_AIRCRAFT_TRAILS = true   # Show speed/direction trail lines on contacts
SWEEP_PERIOD = 6.0            # Seconds per full radar sweep rotation
CONTACT_PERSISTENCE = 5.0     # How long (seconds) a contact stays visible after being swept
                              # Set to 0 for flash-only with no fade

[Audio]
ATC_STREAM_URL =              # URL of a live ATC audio stream (leave blank to disable)
AUTO_START = false            # Start ATC stream automatically on launch

[Location]
LAT = 0.0                     # Your latitude
LON = 0.0                     # Your longitude
AREA_NAME = UNKNOWN           # Name displayed in the header
RADIUS_NM = 60                # Initial radar range (nautical miles)
                              # Can also be changed live with the [-]/[+] buttons

[Display]
FPS = 6                       # Frames per second (lower = less CPU on Pi)
MAX_TABLE_ROWS = 10           # Max aircraft rows in the data table
FONT_PATH = fonts/TerminusTTF-4.49.3.ttf
BACKGROUND_PATH =             # Optional background image path
TRAIL_MIN_LENGTH = 8          # Minimum aircraft trail length (pixels at base resolution)
TRAIL_MAX_LENGTH = 25         # Maximum aircraft trail length
TRAIL_MAX_SPEED = 500         # Speed (knots) at which trail reaches maximum length
HEADER_FONT_SIZE = 32
RADAR_FONT_SIZE = 28
TABLE_FONT_SIZE = 28
INSTRUCTION_FONT_SIZE = 28
# Note: SCREEN_WIDTH/SCREEN_HEIGHT are ignored — the app auto-detects your screen resolution
```

## How the radar sweep works

Aircraft contacts only appear when the rotating sweep line passes over them, just like real radar. Between sweeps, contacts fade from full brightness to near-black over the duration set by `CONTACT_PERSISTENCE`. The data table also only updates when the sweep hits each aircraft.

Zoom can be changed live using the `[-]` and `[+]` buttons displayed below the radar scope, or with the scroll wheel. Available ranges: 10, 20, 30, 50, 75, 100, 150, 200, 300 NM. Changing the zoom reloads airport data for the new range automatically.

## Airport overlay

On first run, the app downloads airport and runway data from [OurAirports](https://ourairports.com/) and caches it to `~/.cache/retro-adsb-radar/`. Airports within your radar range are drawn on the scope in amber — large and medium airports show runway shapes and ICAO labels, small airports show as squares.

## Troubleshooting

**RTL-SDR device busy on startup:** another process has the dongle. Run `pkill -f dump1090` and try again.

**No contacts appearing:** wait up to one full sweep period (default 6 seconds) for the sweep to paint all contacts for the first time.

**SDL dependency errors:** install missing libraries:
```bash
sudo apt install libsdl2-2.0-0 libsdl2-ttf-2.0-0 libsdl2-image-2.0-0
```

## License

- Project code: MIT License (see `LICENSE`)
- Fonts: SIL Open Font License Version 1.1 (see `fonts/` directory)
