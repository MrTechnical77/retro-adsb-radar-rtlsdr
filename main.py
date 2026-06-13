# Set SDL_AUDIODRIVER to guarantee no device is opened for audio output
import os
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import sys
import time
import subprocess
import shutil
import threading
import http.server
from datetime import datetime
from typing import Optional

import config
import utils
from airport_data import load_airports
from audio_manager import AudioManager
from data_fetcher import AircraftTracker
from ui_components import RadarScope, DataTable
from settings_menu import SettingsMenu

def find_dump1090():
    """Find the dump1090 binary."""
    # Check PATH first
    path = shutil.which("dump1090")
    if path:
        return path
    # Common locations
    candidates = [
        os.path.expanduser("~/dump1090/dump1090"),
        "/usr/local/bin/dump1090",
        "/usr/bin/dump1090",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None

DUMP1090_JSON_DIR = "/tmp/dump1090"

def start_dump1090():
    """Launch dump1090. Returns the process, or None if RTL-SDR not available."""
    binary = find_dump1090()
    if not binary:
        print("WARNING: dump1090 not found.")
        return None
    os.makedirs(DUMP1090_JSON_DIR, exist_ok=True)
    print(f"Starting dump1090 from {binary}...")
    proc = subprocess.Popen(
        [binary, "--net", "--quiet", "--write-json", DUMP1090_JSON_DIR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    if proc.poll() is not None:
        print("WARNING: dump1090 exited early — RTL-SDR likely not connected.")
        return None
    print("dump1090 started.")
    return proc

def start_http_server():
    """Serve dump1090's JSON directory on port 8080."""
    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *args: None  # Suppress access logs
    os.chdir(DUMP1090_JSON_DIR)
    server = http.server.HTTPServer(("localhost", 8080), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("HTTP server started on port 8080.")
    return server

dump1090_proc = None
http_server   = None

def toggle_data_source():
    """Hot-swap between local RTL-SDR (dump1090) and internet fallback."""
    global dump1090_proc, http_server

    if config.USE_INTERNET_FALLBACK:
        # Try to switch back to SDR
        proc = start_dump1090()
        if proc is None:
            print("Cannot switch to SDR — no device found.")
            return
        dump1090_proc = proc
        if http_server is None:
            http_server = start_http_server()
        config.USE_INTERNET_FALLBACK = False
        print("Switched to RTL-SDR source.")
    else:
        # Switch to internet
        if dump1090_proc and dump1090_proc.poll() is None:
            dump1090_proc.terminate()
            try:
                dump1090_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                dump1090_proc.kill()
        dump1090_proc = None
        config.USE_INTERNET_FALLBACK = True
        print("Switched to internet ADS-B source.")

def main():
    """Main application loop"""
    global dump1090_proc, http_server
    print("\nStarting Retro ADS-B Radar...")
    dump1090_proc = start_dump1090()
    if dump1090_proc:
        http_server = start_http_server()
    else:
        print("Falling back to internet ADS-B data via adsb.lol")
        config.USE_INTERNET_FALLBACK = True
    airports = load_airports()
    print(f"Location: {config.AREA_NAME} ({config.LAT}°, {config.LON}°)")
    print(f"Range: {config.RADIUS_NM} NM")
    print(f"Display: {config.SCREEN_WIDTH}x{config.SCREEN_HEIGHT} at {config.FPS} FPS")

    # Initialisation
    pygame.display.init()
    pygame.font.init()
    utils.check_pygame_modules()

    # Auto-detect screen resolution and scale everything accordingly
    info = pygame.display.Info()
    actual_w = info.current_w if info.current_w > 0 else config.SCREEN_WIDTH
    actual_h = info.current_h if info.current_h > 0 else config.SCREEN_HEIGHT
    print(f"Detected screen: {actual_w}x{actual_h}")
    config.apply_scale(actual_w, actual_h)

    # Preload all required fonts into a local dictionary
    print("\nPreloading fonts...")
    font_cache = {
        'header': utils.load_font(config.HEADER_FONT_SIZE),
        'radar': utils.load_font(config.RADAR_FONT_SIZE),
        'table': utils.load_font(config.TABLE_FONT_SIZE),
        'instruction': utils.load_font(config.INSTRUCTION_FONT_SIZE)
    }

    # Display Setup
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
    pygame.display.set_caption(f"{config.AREA_NAME} ADS-B RADAR")
    clock = pygame.time.Clock()
    background = utils.load_background(config.BACKGROUND_PATH) if config.BACKGROUND_PATH else None
    
    # Mouse Visibility Control
    last_mouse_move = time.time()
    MOUSE_HIDE_DELAY = 3.0
    pygame.mouse.set_visible(True)

    # Create Components
    radar_size = min(config.SCREEN_HEIGHT - 120, config.SCREEN_WIDTH // 2 - 50) // 2
    radar    = RadarScope(screen, config.SCREEN_WIDTH // 4, config.SCREEN_HEIGHT // 2 + 35, radar_size)
    table    = DataTable(screen, config.SCREEN_WIDTH // 2 + 20, 80, config.SCREEN_WIDTH // 2 - 30, config.SCREEN_HEIGHT - 100)
    settings = SettingsMenu(screen)

    # Initialise Audio and Data Tracker
    audio = AudioManager(config.ATC_STREAM_URL)
    if audio.initialise() and config.ATC_AUTO_START:
        print("Auto-starting ATC audio...")
        audio.toggle()

    tracker = AircraftTracker()
    tracker.start()

    # Main Loop
    running = True
    while running:
        # Mouse Cursor Visibility
        if time.time() - last_mouse_move > MOUSE_HIDE_DELAY:
            pygame.mouse.set_visible(False)

        # Drawing
        screen.blit(background, (0, 0)) if background else screen.fill(config.BLACK)

        # Header
        current_time = datetime.now().strftime("%H:%M:%S")
        header_text = f"{config.AREA_NAME} {config.LAT}°, {config.LON}° - {current_time}"
        header = font_cache['header'].render(header_text, True, config.AMBER)
        header_rect = header.get_rect(centerx=config.SCREEN_WIDTH // 2, y=15)
        screen.blit(header, header_rect)

        # Radar Title
        radar_title = font_cache['radar'].render("◄ ADS-B RADAR SCOPE ►", True, config.AMBER)
        radar_title_rect = radar_title.get_rect(centerx=config.SCREEN_WIDTH//4, y=config.SCREEN_HEIGHT//2 - radar_size)
        screen.blit(radar_title, radar_title_rect)

        # Components
        radar.draw(tracker.aircraft, airports)
        table.draw(radar.painted_aircraft, tracker.status, tracker.last_update)

        # Data source indicator / toggle button (top-left corner)
        if config.USE_INTERNET_FALLBACK:
            src_text   = "* NET"
            src_colour = config.AMBER
        else:
            src_text   = "* SDR"
            src_colour = config.BRIGHT_GREEN
        src_surf      = font_cache['instruction'].render(src_text, True, src_colour)
        src_btn_rect  = src_surf.get_rect(x=10, y=10)
        # Brighten on hover to show it's clickable
        if src_btn_rect.collidepoint(pygame.mouse.get_pos()):
            src_surf = font_cache['instruction'].render(src_text, True, config.BRIGHT_GREEN)
        screen.blit(src_surf, src_btn_rect)

        # Settings button (below source indicator)
        mouse_pos  = pygame.mouse.get_pos()
        set_surf   = font_cache['instruction'].render('# SET', True,
                     config.BRIGHT_GREEN if pygame.Rect(10, 36, 80, 24).collidepoint(mouse_pos)
                     else config.DIM_GREEN)
        settings_btn_rect = set_surf.get_rect(x=10, y=36)
        screen.blit(set_surf, settings_btn_rect)

        # Settings overlay (drawn on top of everything while open)
        dt = clock.get_time() / 1000.0
        settings.draw(dt)

        # Close button (top-right corner)
        btn_size = max(36, int(44 * config.SCALE))
        close_rect = pygame.Rect(config.SCREEN_WIDTH - btn_size - 8, 8, btn_size, btn_size)
        close_col = config.BRIGHT_GREEN if close_rect.collidepoint(mouse_pos) else config.DIM_GREEN
        pygame.draw.rect(screen, close_col, close_rect, 2)
        x_surf = font_cache['header'].render("X", True, close_col)
        screen.blit(x_surf, x_surf.get_rect(center=close_rect.center))

        # ATC audio button (if enabled)
        audio_rect = None
        if audio and audio.initialised:
            audio_text = f"A: ATC [{'ON' if audio.is_playing() else 'OFF'}]"
            audio_surface = font_cache['instruction'].render(audio_text, True, config.DIM_GREEN)
            audio_rect = audio_surface.get_rect(centerx=config.SCREEN_WIDTH // 4, y=config.SCREEN_HEIGHT - 55)
            audio_col = config.BRIGHT_GREEN if audio_rect.collidepoint(mouse_pos) else config.DIM_GREEN
            audio_surface = font_cache['instruction'].render(audio_text, True, audio_col)
            screen.blit(audio_surface, audio_rect)

        quit_rect = pygame.Rect(0, 0, 0, 0)  # kept for legacy event handling

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # While settings are open, route all input there
            elif settings.is_open and event.type in (
                pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION
            ):
                result = settings.handle_event(event)
                if isinstance(result, set):
                    # Settings were saved — apply side effects
                    if 'reload_airports' in result:
                        airports = load_airports()
                    if 'rebuild_radar' in result:
                        radar._build_background()
                    if 'update_sweep' in result:
                        radar.sweep_speed = 360.0 / config.SWEEP_PERIOD
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    settings.close()

            else:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_q, pygame.K_ESCAPE):
                        running = False
                    elif event.key == pygame.K_a:
                        if audio: audio.toggle()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if not settings.is_open:
                        if radar.handle_event(event):
                            airports = load_airports()
                    mouse_pos = pygame.mouse.get_pos()
                    if close_rect.collidepoint(mouse_pos):
                        running = False
                    elif src_btn_rect.collidepoint(mouse_pos):
                        toggle_data_source()
                    elif settings_btn_rect.collidepoint(mouse_pos):
                        settings.open()
                    elif audio and audio_rect and audio_rect.collidepoint(mouse_pos):
                        audio.toggle()
                    last_mouse_move = time.time()
                    pygame.mouse.set_visible(True)
                elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
                    last_mouse_move = time.time()
                    pygame.mouse.set_visible(True)

        # Update display
        pygame.display.flip()
        clock.tick(config.FPS)

    # Shutdown
    tracker.running = False
    if audio and audio.initialised:
        audio.shutdown()
    if dump1090_proc and dump1090_proc.poll() is None:
        print("Stopping dump1090...")
        dump1090_proc.terminate()
        try:
            dump1090_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dump1090_proc.kill()

    print("Shutting down...")
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    dump1090_proc = None
    try:
        main()
    finally:
        if dump1090_proc and dump1090_proc.poll() is None:
            dump1090_proc.terminate()
            try:
                dump1090_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dump1090_proc.kill()
