"""Ventana principal / salvapantallas multiplataforma de ResoNexuz (Linux, Windows, macOS)."""
from __future__ import annotations

import argparse
import math
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .audio_engine import AudioEngine, Frame
from .config import default_config_path, ensure_user_files, load_config
from .renderer import Renderer, write_png
from .shapes import default_shapes_path, load_shapes

GRACE_S = 0.5
MOUSE_EXIT_PX = 10.0
TITLE = "ResoNexuz"
APP_ID = "resonexuz"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="resonexuz", description="ResoNexuz: visualizador de audio estéreo OpenGL")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--fullscreen", action="store_true", help="pantalla completa / salvapantallas (por defecto)")
    mode.add_argument("--windowed", action="store_true", help="ventana redimensionable de 1280x800")
    mode.add_argument("--wallpaper", action="store_true", help="modo fondo animado (Wayland en Linux; ventana al fondo en Windows/macOS)")
    mode.add_argument("--ui", action="store_true", help="iniciar solo el configurador web local")
    p.add_argument("--with-ui", action="store_true", help="abrir también el configurador web en segundo plano")
    p.add_argument("--port", type=int, default=8765, help="puerto del configurador web (por defecto 8765)")
    p.add_argument("--host", default="127.0.0.1", help="dirección del configurador web (por defecto 127.0.0.1)")
    p.add_argument("--no-browser", action="store_true", help="no abrir el navegador automáticamente con --ui")
    p.add_argument("--diag", action="store_true", help="telemetría del DSP en consola")
    p.add_argument("--demo", action="store_true", help="audio sintético estéreo (sin capturar el sistema)")
    p.add_argument("--headless", action="store_true", help="sin ventana: solo análisis de audio (implica --diag)")
    p.add_argument("--seconds", type=float, default=0.0, help="salir solo tras N segundos")
    p.add_argument("--snapshot", type=Path, help="guardar un PNG del fotograma antes de salir")
    p.add_argument("--config", type=Path, help="ruta alternativa de config.toml")
    return p.parse_args(argv)


class Diag:
    """Telemetría ASCII del DSP (~10 Hz)."""

    def __init__(self) -> None:
        self.last = 0.0
        self.counts = (0, 0)
        self.flash = {1: 0.0, 2: 0.0}
        self.tty = sys.stdout.isatty()

    @staticmethod
    def bar(v: float, width: int = 12) -> str:
        n = int(round(max(0.0, min(v, 1.0)) * width))
        return "█" * n + "·" * (width - n)

    def update(self, f: Frame, engine: AudioEngine) -> None:
        now = time.monotonic()
        d = f.dyn
        if d.n_primary != self.counts[0]:
            self.flash[1] = now
        if d.n_secondary != self.counts[1]:
            self.flash[2] = now
        self.counts = (d.n_primary, d.n_secondary)
        if now - self.last < 0.1:
            return
        self.last = now
        p1 = "PEAK_1" if now - self.flash[1] < 0.2 else "      "
        p2 = "PEAK_2" if now - self.flash[2] < 0.2 else "      "
        line = (
            f"BPM {d.bpm:5.1f} {self.bar(d.beat_speed)} | cent {d.centroid_hz:6.0f} Hz | "
            f"hue {d.base_hue:4.2f} bal {f.stereo_balance:+4.2f} | rms {engine.rms:6.4f} | "
            f"P1 {self.bar(d.peak_primary, 8)} {p1} P2 {self.bar(d.peak_secondary, 8)} {p2} | idle {f.idle:3.1f}"
        )
        print("\r" + line if self.tty else line, end="" if self.tty else "\n", flush=True)


def run_headless(engine: AudioEngine, args: argparse.Namespace, stop: list[bool]) -> None:
    diag, start = Diag(), time.monotonic()
    while not stop[0] and not (args.seconds and time.monotonic() - start >= args.seconds):
        diag.update(engine.get_frame(), engine)
        time.sleep(0.016)
    print()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _send_window_to_bottom_windows(window) -> None:
    """Coloca una ventana sin bordes detrás de las demás en Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        import glfw

        hwnd = glfw.get_win32_window(window)
        if hwnd:
            user32 = ctypes.windll.user32
            HWND_BOTTOM = 1
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


def _target_fps(cfg: dict, wallpaper_win: bool, idle: float) -> int:
    q = cfg.get("quality", {})
    idle_fps = int(q.get("idle_fps", 15))
    max_fps = int(q.get("max_fps", 60))
    if idle > 0.92 and idle_fps > 0:
        return idle_fps
    if wallpaper_win:
        wp_fps = max(10, int(cfg.get("wallpaper", {}).get("fps", 60)))
        return min(wp_fps, max_fps) if max_fps > 0 else wp_fps
    return max_fps


def run_window(engine: AudioEngine, cfg: dict, cfg_path: Path, shapes_path: Path,
               args: argparse.Namespace, stop: list[bool]) -> int:
    import glfw
    import moderngl

    if sys.platform.startswith("linux"):
        try:
            glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_WAYLAND)
        except (AttributeError, glfw.GLFWError):
            pass
    if not glfw.init():
        if sys.platform.startswith("linux"):
            glfw.init_hint(glfw.PLATFORM, glfw.ANY_PLATFORM)
        if not glfw.init():
            print("[resonexuz] No se pudo iniciar GLFW.", file=sys.stderr)
            return 1

    wallpaper_win = bool(args.wallpaper)
    fullscreen = not args.windowed and not wallpaper_win
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
    glfw.window_hint(glfw.DECORATED, glfw.FALSE if (fullscreen or wallpaper_win) else glfw.TRUE)
    if sys.platform == "darwin":
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)
    if hasattr(glfw, "WAYLAND_APP_ID"):
        glfw.window_hint_string(glfw.WAYLAND_APP_ID, APP_ID)

    monitors = glfw.get_monitors()
    monitor = monitors[min(int(cfg["display"]["monitor"]), len(monitors) - 1)] if monitors else None
    if fullscreen and monitor is not None:
        mode = glfw.get_video_mode(monitor)
        window = glfw.create_window(mode.size.width, mode.size.height, TITLE, monitor, None)
    elif wallpaper_win and monitor is not None:
        mode = glfw.get_video_mode(monitor)
        mx, my = glfw.get_monitor_pos(monitor)
        window = glfw.create_window(mode.size.width, mode.size.height, TITLE, None, None)
        if window:
            glfw.set_window_pos(window, mx, my)
    else:
        window = glfw.create_window(1280, 800, TITLE, None, None)

    if not window:
        glfw.terminate()
        print("[resonexuz] No se pudo crear la ventana OpenGL 3.3 core.", file=sys.stderr)
        return 1

    glfw.make_context_current(window)
    glfw.swap_interval(1)
    if fullscreen:
        glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_HIDDEN)
    if wallpaper_win:
        _send_window_to_bottom_windows(window)

    start = time.monotonic()
    exit_flag = [False]
    cursor_ref: list[tuple[float, float] | None] = [None]
    fb_size = list(glfw.get_framebuffer_size(window))

    def armed() -> bool:
        return time.monotonic() - start > GRACE_S

    def on_key(_w, key: int, *_a) -> None:
        if wallpaper_win:
            return
        if fullscreen and armed():
            exit_flag[0] = True
        elif key == glfw.KEY_ESCAPE and armed():
            exit_flag[0] = True

    def on_button(*_a) -> None:
        if armed() and fullscreen:
            exit_flag[0] = True

    def on_cursor(_w, x: float, y: float) -> None:
        if not fullscreen:
            return
        if cursor_ref[0] is None or not armed():
            cursor_ref[0] = (x, y)
        elif math.hypot(x - cursor_ref[0][0], y - cursor_ref[0][1]) > MOUSE_EXIT_PX:
            exit_flag[0] = True

    def on_fb_resize(_w, w: int, h: int) -> None:
        fb_size[0], fb_size[1] = w, h

    def on_monitor_event(_mon, event: int) -> None:
        if fullscreen and event == glfw.DISCONNECTED:
            exit_flag[0] = True

    glfw.set_key_callback(window, on_key)
    glfw.set_mouse_button_callback(window, on_button)
    glfw.set_cursor_pos_callback(window, on_cursor)
    glfw.set_framebuffer_size_callback(window, on_fb_resize)
    glfw.set_monitor_callback(on_monitor_event)

    ctx = moderngl.create_context()
    shapes_cfg = load_shapes(shapes_path)
    renderer = Renderer(ctx, cfg, shapes_cfg)
    cfg_mt = _mtime(cfg_path)
    shp_mt = _mtime(shapes_path)
    last_reload = start

    diag = Diag() if args.diag else None
    snapped = False
    try:
        while not glfw.window_should_close(window) and not exit_flag[0] and not stop[0]:
            glfw.poll_events()
            now = time.monotonic()
            if args.seconds and now - start >= args.seconds:
                break
            if now - last_reload > 0.5:
                last_reload = now
                cm = _mtime(cfg_path)
                if cm and cm != cfg_mt:
                    cfg_mt = cm
                    cfg = load_config(cfg_path)
                    engine.update_config(cfg)
                    renderer.update_config(cfg)
                sm = _mtime(shapes_path)
                if sm and sm != shp_mt:
                    shp_mt = sm
                    renderer.update_shapes(load_shapes(shapes_path))

            w, h = fb_size[0], fb_size[1]
            if w > 0 and h > 0:
                f = engine.get_frame()
                ctx.screen.use()
                renderer.draw(f, w, h, now - start)
                if args.snapshot and not snapped and now - start > max(1.5, args.seconds * 0.6 if args.seconds else 1.5):
                    write_png(args.snapshot, ctx.screen.read(viewport=(0, 0, w, h), components=3, alignment=1), w, h)
                    snapped = True
                glfw.swap_buffers(window)
                if diag:
                    diag.update(f, engine)
                tfps = _target_fps(cfg, wallpaper_win, f.idle)
                if tfps > 0:
                    wait_s = (1.0 / tfps) - (time.monotonic() - now)
                    if args.seconds:
                        wait_s = min(wait_s, max(0.0, start + args.seconds - time.monotonic()))
                    if wait_s > 0.001:
                        time.sleep(wait_s)
            else:
                time.sleep(0.05)
    finally:
        renderer.release()
        glfw.destroy_window(window)
        glfw.terminate()
        if diag:
            print()
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_user_files()
    cfg_path = args.config or default_config_path()
    shapes_path = default_shapes_path()

    if args.ui:
        from .web_ui import serve_ui
        return serve_ui(host=args.host, port=args.port, cfg_path=cfg_path, shapes_path=shapes_path,
                        open_browser=not args.no_browser)

    if args.wallpaper and sys.platform.startswith("linux"):
        from .wallpaper import try_run_wayland_wallpaper
        rc = try_run_wayland_wallpaper(cfg_path=cfg_path, shapes_path=shapes_path, seconds=args.seconds,
                                       demo=args.demo, snapshot=args.snapshot)
        if rc is not None:
            return rc

    if args.with_ui:
        from .web_ui import start_ui_background
        url = start_ui_background(host=args.host, port=args.port, cfg_path=cfg_path, shapes_path=shapes_path)
        print(f"[resonexuz] Configurador web en {url}")
        if not args.no_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    if args.headless:
        args.diag = True
    cfg = load_config(cfg_path)
    engine = AudioEngine(cfg)
    stop = [False]

    def on_signal(_sig, _frm) -> None:
        stop[0] = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    engine.start(demo=args.demo)
    try:
        if args.headless:
            run_headless(engine, args, stop)
            return 0
        return run_window(engine, cfg, cfg_path, shapes_path, args, stop)
    finally:
        engine.stop()
