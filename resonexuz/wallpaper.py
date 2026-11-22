"""Fondo de pantalla animado nativo en Wayland (GTK4 + gtk4-layer-shell) para Linux."""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from .audio_engine import AudioEngine, Frame
from .config import default_config_path, load_config
from .renderer import Renderer, write_png
from .shapes import default_shapes_path, load_shapes


def _create_gl_context():
    """Detecta el contexto EGL/GLX actual de GTK4 en cada ventana sin usar _store.default_context."""
    from collections import deque
    import moderngl
    from _moderngl import DefaultLoader

    loader = DefaultLoader()
    ctx = moderngl.Context.__new__(moderngl.Context)
    ctx.mglo, ctx.version_code = moderngl.mgl.create_context(context=loader)
    ctx._info = None
    ctx._extensions = None
    ctx.extra = None
    ctx._gc_mode = None
    ctx._objects = deque()
    ctx._screen = ctx.detect_framebuffer(0)
    ctx.fbo = ctx.detect_framebuffer()
    ctx.mglo.fbo = ctx.fbo.mglo
    return ctx


def try_run_wayland_wallpaper(cfg_path: Path | None = None, shapes_path: Path | None = None,
                              fps: int | None = None, seconds: float = 0.0,
                              demo: bool = False, snapshot: Path | None = None) -> int | None:
    """Inicia el fondo Wayland si GTK4 y gtk4-layer-shell están disponibles; si no, devuelve None."""
    if not sys.platform.startswith("linux") or not os.environ.get("WAYLAND_DISPLAY"):
        return None
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell as LayerShell
        try:
            from gi.repository import GLibUnix
        except ImportError:
            GLibUnix = None
    except Exception:
        return None

    class WallpaperWindow(Gtk.Window):
        def __init__(self, app: "WallpaperApp", monitor: Gdk.Monitor) -> None:
            super().__init__(application=app)
            self.app = app
            self.monitor = monitor
            self.ctx = None
            self.renderer: Renderer | None = None
            self.cfg_gen = -1
            self.shape_gen = -1
            self._last_err_t = 0.0

            LayerShell.init_for_window(self)
            LayerShell.set_namespace(self, "resonexuz-wallpaper")
            LayerShell.set_layer(self, LayerShell.Layer.BOTTOM)
            LayerShell.set_monitor(self, monitor)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
                LayerShell.set_anchor(self, edge, True)
            LayerShell.set_exclusive_zone(self, -1)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)

            self.area = Gtk.GLArea()
            self.area.set_use_es(False)
            self.area.set_required_version(3, 3)
            self.area.set_has_depth_buffer(False)
            self.area.set_auto_render(False)
            self.area.connect("realize", self.on_realize)
            self.area.connect("unrealize", self.on_unrealize)
            self.area.connect("render", self.on_render)
            self.set_child(self.area)

        def on_realize(self, area: Gtk.GLArea) -> None:
            area.make_current()
            if area.get_error() is not None:
                print(f"[resonexuz] GLArea: {area.get_error()}", file=sys.stderr)

        def on_unrealize(self, area: Gtk.GLArea) -> None:
            if self.ctx is None and self.renderer is None:
                return
            try:
                area.make_current()
                if self.renderer is not None:
                    self.renderer.release()
                    self.renderer = None
                if self.ctx is not None:
                    self.ctx.release()
                    self.ctx = None
            except Exception as exc:
                print(f"[resonexuz] Error liberando GL: {exc}", file=sys.stderr)

        def on_render(self, area: Gtk.GLArea, _gdk_ctx) -> bool:
            try:
                area.make_current()
                if area.get_error() is not None:
                    return False
                if self.ctx is None:
                    self.ctx = _create_gl_context()
                    self.renderer = Renderer(self.ctx, self.app.cfg, self.app.shapes_cfg)
                    self.cfg_gen = self.app.cfg_gen
                    self.shape_gen = self.app.shape_gen

                if self.cfg_gen != self.app.cfg_gen:
                    self.renderer.update_config(self.app.cfg)
                    self.cfg_gen = self.app.cfg_gen
                if self.shape_gen != self.app.shape_gen:
                    self.renderer.update_shapes(self.app.shapes_cfg)
                    self.shape_gen = self.app.shape_gen

                scale = max(1, area.get_scale_factor())
                w, h = area.get_width() * scale, area.get_height() * scale
                if w > 0 and h > 0:
                    fbo = self.ctx.detect_framebuffer()
                    fbo.use()
                    t = time.monotonic() - self.app.start
                    self.renderer.draw(self.app.frame(), w, h, t)
                    snap = self.app.snapshot
                    if snap and t > 2.5 and not self.app.snapped:
                        self.app.snapped = True
                        write_png(snap, fbo.read(components=3, alignment=1), w, h)
            except Exception as exc:
                now = time.monotonic()
                if now - self._last_err_t > 5.0:
                    self._last_err_t = now
                    print(f"[resonexuz] Error de render: {exc}", file=sys.stderr)
                return False
            return True

    class WallpaperApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.resonexuz.wallpaper")
            self.cfg_path = cfg_path or default_config_path()
            self.shapes_path = shapes_path or default_shapes_path()
            self.cfg = load_config(self.cfg_path)
            self.shapes_cfg = load_shapes(self.shapes_path)
            self.cfg_gen = 0
            self.shape_gen = 0
            self._cfg_mtime = self._mtime(self.cfg_path)
            self._shapes_mtime = self._mtime(self.shapes_path)
            self.fps_override = fps
            self.fps = max(10, fps or int(self.cfg.get("wallpaper", {}).get("fps", 60)))
            self.seconds = seconds
            self.demo = demo
            self.snapshot = snapshot
            self.snapped = False
            self.engine = AudioEngine(self.cfg)
            self.start = time.monotonic()
            self._frame: Frame | None = None
            self._frame_t = 0.0
            self.windows: dict[int, WallpaperWindow] = {}
            self._sync_timer_id: int | None = None
            self._tick_timer_id: int | None = None
            self._reload_timer_id: int | None = None

        @staticmethod
        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        def frame(self) -> Frame:
            now = time.monotonic()
            if self._frame is None or now - self._frame_t > 0.004:
                self._frame, self._frame_t = self.engine.get_frame(), now
            return self._frame

        def do_activate(self) -> None:
            if not LayerShell.is_supported():
                print("[resonexuz] El compositor no soporta wlr-layer-shell.", file=sys.stderr)
                self.quit()
                return
            self.hold()
            self.engine.start(demo=self.demo)
            self.sync_monitors()
            Gdk.Display.get_default().get_monitors().connect("items-changed", lambda *_: self.schedule_sync_monitors())
            self._tick_timer_id = GLib.timeout_add(self._interval(), self.tick)
            self._reload_timer_id = GLib.timeout_add(500, self.check_hot_reload)
            if self.seconds:
                GLib.timeout_add(int(self.seconds * 1000), self.quit_all)
            for sig in (signal.SIGINT, signal.SIGTERM):
                if GLibUnix is not None:
                    GLibUnix.signal_add(GLib.PRIORITY_HIGH, sig, self.quit_all)
                else:
                    GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self.quit_all)

        def schedule_sync_monitors(self) -> None:
            if self._sync_timer_id is not None:
                GLib.source_remove(self._sync_timer_id)
            self._sync_timer_id = GLib.timeout_add(350, self._debounced_sync)

        def _debounced_sync(self) -> bool:
            self._sync_timer_id = None
            self.sync_monitors()
            return False

        def sync_monitors(self) -> None:
            monitors = Gdk.Display.get_default().get_monitors()
            current: dict[int, Gdk.Monitor] = {}
            pending_geom = False
            for i in range(monitors.get_n_items()):
                mon = monitors.get_item(i)
                if mon is None or (hasattr(mon, "is_valid") and not mon.is_valid()):
                    continue
                geom = mon.get_geometry()
                if geom.width <= 0 or geom.height <= 0:
                    pending_geom = True
                    continue
                current[hash(mon)] = mon

            for key in list(self.windows.keys()):
                if key not in current:
                    self.windows.pop(key).close()

            for key, mon in current.items():
                if key not in self.windows:
                    win = WallpaperWindow(self, mon)
                    win.present()
                    self.windows[key] = win

            if pending_geom and self._sync_timer_id is None:
                self._sync_timer_id = GLib.timeout_add(600, self._debounced_sync)

        def check_hot_reload(self) -> bool:
            cm = self._mtime(self.cfg_path)
            if cm and cm != self._cfg_mtime:
                self._cfg_mtime = cm
                self.cfg = load_config(self.cfg_path)
                self.engine.update_config(self.cfg)
                if self.fps_override is None:
                    self.fps = max(10, int(self.cfg.get("wallpaper", {}).get("fps", 60)))
                self.cfg_gen += 1

            sm = self._mtime(self.shapes_path)
            if sm and sm != self._shapes_mtime:
                self._shapes_mtime = sm
                self.shapes_cfg = load_shapes(self.shapes_path)
                self.shape_gen += 1
            return True

        def _interval(self) -> int:
            return max(8, int(1000 / self.fps))

        def tick(self) -> bool:
            for win in list(self.windows.values()):
                if win.get_realized() and win.area.get_realized():
                    win.area.queue_render()
            idle = self._frame.idle if self._frame is not None else 0.0
            self._tick_timer_id = GLib.timeout_add(self._interval() * (3 if idle > 0.95 else 1), self.tick)
            return False

        def quit_all(self) -> bool:
            for tid in (self._sync_timer_id, self._tick_timer_id, self._reload_timer_id):
                if tid is not None:
                    GLib.source_remove(tid)
            self._sync_timer_id = self._tick_timer_id = self._reload_timer_id = None
            for win in list(self.windows.values()):
                win.close()
            self.windows.clear()
            self.engine.stop()
            self.release()
            self.quit()
            return False

    return WallpaperApp().run([])
