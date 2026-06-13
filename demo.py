"""
Demo mode — runs the radar UI with simulated aircraft and a 52-second auto-sequence
that showcases all major features. No RTL-SDR required.

On every run, captures a GIF of the first complete cycle and saves it to
images/demo.gif, then continues looping (press Q / ESC / close window to quit).

Usage:
    python3 demo.py [--no-record]

    --no-record   Skip GIF capture (useful for testing or on slow machines).
"""
import os, sys, time, math, argparse
from datetime import datetime

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

# ── parse args before anything touches pygame ──────────────────────────────
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--no-record', action='store_true')
_args, _ = _parser.parse_known_args()
RECORD = not _args.no_record

if RECORD:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — install with:  pip install Pillow")
        print("Running without GIF recording (use --no-record to silence this).")
        RECORD = False

import config
# Force demo-friendly defaults before anything else loads
config.USE_INTERNET_FALLBACK = False
config.SWEEP_PERIOD          = 6.0
config.CONTACT_PERSISTENCE   = 5.0
config.SHOW_AIRCRAFT_TRAILS  = True
config.BLINK_MILITARY        = True
config.RADIUS_NM             = 60

import utils
from airport_data    import load_airports
from audio_manager   import AudioManager
from demo_tracker    import DemoAircraftTracker
from ui_components   import RadarScope, DataTable, ZOOM_STEPS
from settings_menu   import SettingsMenu

# ── GIF recording constants ─────────────────────────────────────────────────
DEMO_W, DEMO_H = 960, 640          # fixed window size for recording
GIF_FPS        = 6                  # samples per second in output GIF
GIF_SCALE      = 0.5               # scale factor → 480×320 final GIF
_REPO_DIR      = os.path.dirname(os.path.abspath(__file__))
GIF_PATH       = os.path.join(_REPO_DIR, 'images', 'demo.gif')

# ── Demo sequence ───────────────────────────────────────────────────────────
DEMO_DURATION = 52   # seconds before loop

_sequence_built = False
_sequence = []

def _build_sequence(radar):
    global _sequence, _sequence_built
    _sequence_built = True
    _sequence = [
        ( 0,  8,  "Animated radar sweep — contacts paint as the line passes",        None),
        ( 8, 10,  "Contacts fade between sweeps — just like real radar",              None),
        (10, 13,  "Zooming out…",                                                     lambda: _set_zoom(radar, 100)),
        (13, 17,  "Adjustable range — tap [-]/[+] or scroll wheel (10–300 NM)",       None),
        (17, 20,  "Zooming back in…",                                                 lambda: _set_zoom(radar, 60)),
        (20, 26,  "Airport overlay — runways drawn to scale in amber",                None),
        (26, 30,  "Large & medium airports labelled; small airports hidden past 30NM",None),
        (30, 34,  "Military contacts blink red and are always labelled",              None),
        (34, 38,  "Hot-swap between RTL-SDR and internet ADS-B — tap ◉ SDR / ◉ NET", None),
        (38, 44,  "All settings editable live — tap ⚙ SET",                          None),
        (44, 48,  "Changes apply instantly — no restart needed",                      None),
        (48, 52,  "Auto-scales to any screen size",                                   None),
    ]
    return _sequence


def _set_zoom(radar, nm):
    config.RADIUS_NM = nm
    radar._painted.clear()
    radar._build_background()


# ── Callout renderer ─────────────────────────────────────────────────────────
CALLOUT_FADE  = 0.8
CALLOUT_HOLD  = 0.6

def _draw_callout(screen, font, text, t_in_step, step_dur):
    fade_dur = min(CALLOUT_FADE, step_dur * (1 - CALLOUT_HOLD) / 2)
    if t_in_step < fade_dur:
        alpha = int(255 * t_in_step / fade_dur)
    elif t_in_step > step_dur - fade_dur:
        alpha = int(255 * (step_dur - t_in_step) / fade_dur)
    else:
        alpha = 255

    W, H  = screen.get_size()
    bar_h = max(40, int(50 * config.SCALE))
    bar   = pygame.Surface((W, bar_h), pygame.SRCALPHA)
    bar.fill((0, 0, 0, min(200, alpha)))
    screen.blit(bar, (0, H - bar_h))

    surf = font.render(text, True, (*config.AMBER, alpha))
    screen.blit(surf, surf.get_rect(centerx=W // 2, centery=H - bar_h // 2))

    wm = font.render("DEMO MODE", True, (*config.DIM_GREEN, 160))
    screen.blit(wm, (W - wm.get_width() - 10, 10))


# ── GIF save ─────────────────────────────────────────────────────────────────
def _save_gif(frames):
    if not frames:
        return
    os.makedirs(os.path.dirname(GIF_PATH), exist_ok=True)
    gw = int(DEMO_W * GIF_SCALE)
    gh = int(DEMO_H * GIF_SCALE)
    print(f"\nSaving demo GIF  ({len(frames)} frames @ {GIF_FPS}fps → {gw}×{gh})…")
    pil_frames = []
    for surf_arr in frames:
        img = Image.fromarray(surf_arr.transpose(1, 0, 2))   # (W,H,3) → (H,W,3)
        img = img.resize((gw, gh), Image.LANCZOS)
        pil_frames.append(img)

    pil_frames[0].save(
        GIF_PATH,
        save_all     = True,
        append_images= pil_frames[1:],
        duration     = int(1000 / GIF_FPS),
        loop         = 0,
        optimize     = True,
    )
    kb = os.path.getsize(GIF_PATH) // 1024
    print(f"GIF saved → {GIF_PATH}  ({kb} KB)")


# ── Main demo loop ────────────────────────────────────────────────────────────
def main():
    print("\n🎬  Retro ADS-B Radar — DEMO MODE")
    if RECORD:
        print(f"    Will record GIF to images/demo.gif after {DEMO_DURATION}s.")
    print("    Press Q or ESC to quit.\n")

    pygame.display.init()
    pygame.font.init()
    utils.check_pygame_modules()

    # Use a fixed windowed size so the GIF has consistent dimensions.
    # On the Pi the app uses FULLSCREEN|SCALED; demo.py is desktop-first.
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
    table    = DataTable(screen, DEMO_W // 2 + 20, 80,
                         DEMO_W // 2 - 30, DEMO_H - 100)
    settings = SettingsMenu(screen)

    print("Loading airports…")
    airports = load_airports()

    tracker = DemoAircraftTracker()
    tracker.start()

    sequence         = _build_sequence(radar)
    demo_start       = time.time()
    last_action_step = -1

    # GIF capture state
    gif_frames      = []          # raw numpy arrays (W, H, 3)
    gif_done        = not RECORD  # skip capture if --no-record
    last_capture    = 0.0
    capture_interval= 1.0 / GIF_FPS

    running = True
    while running:
        # Sequence timing (loops after DEMO_DURATION)
        now     = time.time()
        elapsed = (now - demo_start) % DEMO_DURATION
        callout = ''
        t_in_step = step_dur = 0

        for i, (start, end, text, action) in enumerate(sequence):
            if start <= elapsed < end:
                callout   = text
                t_in_step = elapsed - start
                step_dur  = end - start
                if action and last_action_step != i:
                    last_action_step = i
                    action()
                    airports = load_airports()
                break

        # ── Draw ──────────────────────────────────────────────────────────
        screen.fill(config.BLACK)

        current_time = datetime.now().strftime("%H:%M:%S")
        header_text  = f"{config.AREA_NAME} {config.LAT}°, {config.LON}° — {current_time}"
        header       = font_cache['header'].render(header_text, True, config.AMBER)
        screen.blit(header, header.get_rect(centerx=DEMO_W // 2, y=15))

        title = font_cache['radar'].render("◄ ADS-B RADAR SCOPE ►", True, config.AMBER)
        screen.blit(title, title.get_rect(
            centerx=DEMO_W // 4,
            y=DEMO_H // 2 - radar_size))

        radar.draw(tracker.aircraft, airports)
        table.draw(radar.painted_aircraft, tracker.status, tracker.last_update)
        settings.draw(clock.get_time() / 1000.0)

        src_surf = font_cache['instruction'].render("◉ SDR", True, config.BRIGHT_GREEN)
        screen.blit(src_surf, (10, 10))
        set_surf = font_cache['instruction'].render('⚙ SET', True, config.DIM_GREEN)
        screen.blit(set_surf, (10, 36))

        if callout:
            _draw_callout(screen, font_cache['instruction'], callout, t_in_step, step_dur)

        pygame.display.flip()
        clock.tick(config.FPS)

        # ── GIF frame capture ─────────────────────────────────────────────
        if not gif_done:
            if now - last_capture >= capture_interval:
                last_capture = now
                gif_frames.append(pygame.surfarray.array3d(screen).copy())

            # Detect end of first cycle and save
            elapsed_total = now - demo_start
            if elapsed_total >= DEMO_DURATION:
                _save_gif(gif_frames)
                gif_done = True

        # ── Events ────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

    # If user quit before the GIF was saved, save what we have
    if RECORD and not gif_done and len(gif_frames) > 10:
        _save_gif(gif_frames)

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
