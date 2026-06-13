"""
Demo mode — runs the radar UI with simulated aircraft for one sweep cycle,
records images/demo.gif, then exits.

Usage:
    python3 demo.py [--no-record]
"""
import os, sys, time, argparse

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--no-record', action='store_true')
_args, _ = _parser.parse_known_args()
RECORD = not _args.no_record

if RECORD:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — run: pip install Pillow")
        RECORD = False

import config
config.USE_INTERNET_FALLBACK = False
config.SWEEP_PERIOD          = 6.0
config.CONTACT_PERSISTENCE   = 5.0
config.SHOW_AIRCRAFT_TRAILS  = True
config.BLINK_MILITARY        = True
config.RADIUS_NM             = 30

import utils
from airport_data  import load_airports
from audio_manager import AudioManager
from demo_tracker  import DemoAircraftTracker
from ui_components import RadarScope, DataTable
from settings_menu import SettingsMenu
from datetime import datetime

DEMO_W, DEMO_H  = 960, 640
WARMUP_SECS     = 14           # run silently so all contacts paint before recording starts
RECORD_SECS     = 12           # exactly 2 sweep periods → seamless loop
GIF_FPS         = 6
GIF_SCALE       = 0.5          # → 480×320
_REPO_DIR       = os.path.dirname(os.path.abspath(__file__))
GIF_PATH        = os.path.join(_REPO_DIR, 'images', 'demo.gif')


def _save_gif(frames):
    gw, gh = int(DEMO_W * GIF_SCALE), int(DEMO_H * GIF_SCALE)
    print(f"Saving GIF ({len(frames)} frames → {gw}×{gh})…")
    pil = [Image.fromarray(f.transpose(1, 0, 2)).resize((gw, gh), Image.LANCZOS)
           for f in frames]
    pil[0].save(GIF_PATH, save_all=True, append_images=pil[1:],
                duration=int(1000 / GIF_FPS), loop=0, optimize=True)
    print(f"Saved → {GIF_PATH}  ({os.path.getsize(GIF_PATH)//1024} KB)")


def main():
    pygame.display.init()
    pygame.font.init()
    utils.check_pygame_modules()
    config.apply_scale(DEMO_W, DEMO_H)

    font_cache = {
        'header':      utils.load_font(config.HEADER_FONT_SIZE),
        'radar':       utils.load_font(config.RADAR_FONT_SIZE),
        'table':       utils.load_font(config.TABLE_FONT_SIZE),
        'instruction': utils.load_font(config.INSTRUCTION_FONT_SIZE),
    }

    screen = pygame.display.set_mode((DEMO_W, DEMO_H))
    pygame.display.set_caption("Retro ADS-B Radar — Demo")
    clock = pygame.time.Clock()

    radar_size = min(DEMO_H - 120, DEMO_W // 2 - 50) // 2
    radar    = RadarScope(screen, DEMO_W // 4, DEMO_H // 2 + 35, radar_size)
    table    = DataTable(screen, DEMO_W // 2 + 20, 80, DEMO_W // 2 - 30, DEMO_H - 100)
    settings = SettingsMenu(screen)

    airports = load_airports()
    tracker  = DemoAircraftTracker()
    tracker.start()

    gif_frames    = []
    last_capture  = 0.0
    start         = time.time()
    record_start  = None
    running       = True

    print("Warming up…")
    if RECORD:
        print(f"  Will record {RECORD_SECS}s after {WARMUP_SECS}s warmup.")

    while running:
        now = time.time()

        screen.fill(config.BLACK)

        header = font_cache['header'].render(
            f"{config.AREA_NAME} {config.LAT}°, {config.LON}° — {datetime.now().strftime('%H:%M:%S')}",
            True, config.AMBER)
        screen.blit(header, header.get_rect(centerx=DEMO_W // 2, y=15))

        title = font_cache['radar'].render("◄ ADS-B RADAR SCOPE ►", True, config.AMBER)
        screen.blit(title, title.get_rect(centerx=DEMO_W // 4, y=DEMO_H // 2 - radar_size))

        radar.draw(tracker.aircraft, airports)
        table.draw(radar.painted_aircraft, tracker.status, tracker.last_update)
        settings.draw(clock.get_time() / 1000.0)

        screen.blit(font_cache['instruction'].render("◉ SDR", True, config.BRIGHT_GREEN), (10, 10))
        screen.blit(font_cache['instruction'].render("⚙ SET", True, config.DIM_GREEN),    (10, 36))

        # "DEMO MODE" watermark
        wm = font_cache['instruction'].render("DEMO MODE", True, (*config.DIM_GREEN, 160))
        screen.blit(wm, (DEMO_W - wm.get_width() - 10, 10))

        pygame.display.flip()
        clock.tick(60)

        elapsed = now - start

        if RECORD:
            if record_start is None:
                # Wait for warmup, then wait for sweep to cross 0° for a clean loop start
                if elapsed >= WARMUP_SECS and radar.sweep_angle < 5:
                    record_start = now
                    print("Recording…")
            else:
                if now - last_capture >= 1.0 / GIF_FPS:
                    last_capture = now
                    gif_frames.append(pygame.surfarray.array3d(screen).copy())
                if now - record_start >= RECORD_SECS:
                    _save_gif(gif_frames)
                    running = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

    if RECORD and gif_frames and record_start and now - record_start < RECORD_SECS:
        _save_gif(gif_frames)  # save what we have if user quit early

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
