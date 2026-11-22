"""Configurador web local integrado para ResoNexuz (solo biblioteca estándar)."""
from __future__ import annotations

import copy
import json
import math
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import PKG_DIR, default_config_path, load_config, serialize_toml
from .shapes import PRESETS_2D, SHAPES_3D, default_shapes_path, load_shapes

WEB_HTML = PKG_DIR / "web" / "index.html"


def _clamp(val: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v)) if math.isfinite(v) else default


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _validate_level(dflt: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dflt)
    out["name"] = str(raw.get("name") or out["name"])[:40]
    out["enabled"] = bool(raw.get("enabled", out["enabled"]))
    mode = str(raw.get("mode", out["mode"]))
    out["mode"] = mode if mode in ("preset", "custom", "3d") else "preset"
    preset = str(raw.get("preset", out["preset"]))
    out["preset"] = preset if preset in PRESETS_2D else "circle"
    out["closed"] = bool(raw.get("closed", out["closed"]))
    s3 = str(raw.get("shape_3d", out["shape_3d"]))
    out["shape_3d"] = s3 if s3 in SHAPES_3D else "sphere"
    out["rot_speed"] = round(_clamp(raw.get("rot_speed"), 0.0, 5.0, out["rot_speed"]), 3)
    try:
        out["rot_dir"] = -1 if int(raw.get("rot_dir", out["rot_dir"])) < 0 else 1
    except (TypeError, ValueError):
        out["rot_dir"] = 1
    ax = str(raw.get("rot_axis", out["rot_axis"]))
    out["rot_axis"] = ax if ax in ("y", "xy", "xyz") else "y"
    out["scale"] = round(_clamp(raw.get("scale"), 0.12, 0.70, out["scale"]), 3)
    out["reactivity"] = round(_clamp(raw.get("reactivity"), 0.0, 3.0, out["reactivity"]), 3)
    out["echo_enabled"] = bool(raw.get("echo_enabled", out["echo_enabled"]))
    out["echo_amp"] = round(_clamp(raw.get("echo_amp"), 0.2, 3.0, out["echo_amp"]), 3)
    out["echo_offset"] = round(_clamp(raw.get("echo_offset"), 0.005, 0.15, out["echo_offset"]), 4)
    out["echo_peak_only"] = bool(raw.get("echo_peak_only", out["echo_peak_only"]))
    out["echo_threshold"] = round(_clamp(raw.get("echo_threshold"), 0.15, 0.95, out["echo_threshold"]), 2)
    cr = str(raw.get("color_role", out["color_role"]))
    out["color_role"] = cr if cr in ("base", "opp1", "opp2") else out["color_role"]

    pts = []
    for p in (raw.get("custom_points") or [])[:400]:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append([round(_clamp(p[0], 0.0, 1.0, 0.0), 4), round(_clamp(p[1], -1.0, 1.0, 0.0), 4)])
    out["custom_points"] = pts
    return out


def _validate_config(raw: dict[str, Any], base_cfg: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cfg = copy.deepcopy(base_cfg)
    a = raw.get("audio") or {}
    if isinstance(a, dict):
        cfg["audio"]["sensitivity"] = round(_clamp(a.get("sensitivity"), 0.2, 3.0, cfg["audio"]["sensitivity"]), 3)
        cfg["audio"]["gamma"] = round(_clamp(a.get("gamma"), 0.25, 1.6, cfg["audio"]["gamma"]), 3)
        cfg["audio"]["silence_rms"] = _clamp(a.get("silence_rms"), 1e-6, 0.05, cfg["audio"]["silence_rms"])
        cfg["audio"]["silence_seconds"] = round(_clamp(a.get("silence_seconds"), 0.0, 10.0, cfg["audio"]["silence_seconds"]), 2)
        cfg["audio"]["stereo_separation"] = round(_clamp(a.get("stereo_separation"), 0.0, 1.0, cfg["audio"]["stereo_separation"]), 3)

    pk = raw.get("peaks") or {}
    if isinstance(pk, dict):
        cfg["peaks"]["primary_ratio"] = round(_clamp(pk.get("primary_ratio"), 1.05, 2.5, cfg["peaks"]["primary_ratio"]), 3)
        cfg["peaks"]["secondary_ratio"] = round(_clamp(pk.get("secondary_ratio"), 1.05, 2.8, cfg["peaks"]["secondary_ratio"]), 3)

    c = raw.get("color") or {}
    if isinstance(c, dict):
        h = str(c.get("harmony", cfg["color"]["harmony"]))
        cfg["color"]["harmony"] = h if h in ("split_complementary", "triadic") else "split_complementary"
        cfg["color"]["history_seconds"] = round(_clamp(c.get("history_seconds"), 5.0, 120.0, cfg["color"]["history_seconds"]), 1)
        cfg["color"]["short_seconds"] = round(_clamp(c.get("short_seconds"), 1.0, 60.0, cfg["color"]["short_seconds"]), 1)
        cfg["color"]["mode_weight"] = round(_clamp(c.get("mode_weight"), 0.0, 1.0, cfg["color"]["mode_weight"]), 2)
        cfg["color"]["short_influence"] = round(_clamp(c.get("short_influence"), 0.0, 0.5, cfg["color"]["short_influence"]), 3)
        cfg["color"]["tempo_influence"] = round(_clamp(c.get("tempo_influence"), 0.0, 0.6, cfg["color"]["tempo_influence"]), 3)
        cfg["color"]["tone_influence"] = round(_clamp(c.get("tone_influence"), 0.0, 0.5, cfg["color"]["tone_influence"]), 3)
        cfg["color"]["hue_smoothing"] = round(_clamp(c.get("hue_smoothing"), 0.005, 0.25, cfg["color"]["hue_smoothing"]), 4)

    v = raw.get("visual") or {}
    if isinstance(v, dict):
        cfg["visual"]["ring_size"] = round(_clamp(v.get("ring_size"), 0.4, 2.0, cfg["visual"]["ring_size"]), 3)
        cfg["visual"]["ring_reactivity"] = round(_clamp(v.get("ring_reactivity"), 0.2, 2.5, cfg["visual"]["ring_reactivity"]), 3)
        cfg["visual"]["particle_density"] = round(_clamp(v.get("particle_density"), 0.3, 2.0, cfg["visual"]["particle_density"]), 3)

    w = raw.get("wallpaper") or {}
    if isinstance(w, dict):
        try:
            cfg["wallpaper"]["fps"] = max(15, min(165, int(w.get("fps", cfg["wallpaper"]["fps"]))))
        except (TypeError, ValueError):
            pass
    return cfg


def build_state(cfg_path: Path, shapes_path: Path) -> dict[str, Any]:
    return {
        "config": load_config(cfg_path),
        "shapes": load_shapes(shapes_path),
        "presets": list(PRESETS_2D),
        "shapes_3d": list(SHAPES_3D),
    }


def save_state(payload: dict[str, Any], cfg_path: Path, shapes_path: Path) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "datos inválidos"
    try:
        if "config" in payload and isinstance(payload["config"], dict):
            cfg = _validate_config(payload["config"], load_config(cfg_path))
            _atomic_write(cfg_path, serialize_toml(cfg))
        if "shapes" in payload and isinstance(payload["shapes"], dict):
            cur = load_shapes(shapes_path)
            raw = payload["shapes"]
            gi = _clamp(raw.get("guide_inner"), 0.08, 0.55, cur["guide_inner"])
            go = _clamp(raw.get("guide_outer"), gi + 0.12, 0.96, cur["guide_outer"])
            cur["guide_inner"] = round(gi, 3)
            cur["guide_outer"] = round(go, 3)
            if isinstance(raw.get("levels"), list):
                for idx, dflt in enumerate(cur["levels"]):
                    if idx < len(raw["levels"]) and isinstance(raw["levels"][idx], dict):
                        cur["levels"][idx] = _validate_level(dflt, raw["levels"][idx])
            _atomic_write(shapes_path, json.dumps(cur, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        return False, f"no se pudo guardar ({exc})"
    return True, "configuración guardada y aplicada en vivo ✓"


def make_server(host: str, port: int, cfg_path: Path, shapes_path: Path) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, WEB_HTML.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, json.dumps(build_state(cfg_path, shapes_path), ensure_ascii=False).encode(), "application/json")
            else:
                self._send(404, b"no encontrado", "text/plain")

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if self.headers.get("X-ResoNexuz") != "1":
                self._send(403, b"cabecera requerida", "text/plain")
                return
            if path != "/api/config":
                self._send(404, b"no encontrado", "text/plain")
                return
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 131072)
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                payload = {}
            ok, msg = save_state(payload, cfg_path, shapes_path)
            self._send(200, json.dumps({"ok": ok, "mensaje": msg}, ensure_ascii=False).encode(), "application/json")

        def log_message(self, *_a) -> None:
            pass

    return ThreadingHTTPServer((host, port), Handler)


def start_ui_background(host: str = "127.0.0.1", port: int = 8765,
                        cfg_path: Path | None = None, shapes_path: Path | None = None) -> str:
    srv = make_server(host, port, cfg_path or default_config_path(), shapes_path or default_shapes_path())
    actual_port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, name="resonexuz-ui", daemon=True).start()
    return f"http://{host}:{actual_port}/"


def serve_ui(host: str = "127.0.0.1", port: int = 8765,
             cfg_path: Path | None = None, shapes_path: Path | None = None, open_browser: bool = True) -> int:
    srv = make_server(host, port, cfg_path or default_config_path(), shapes_path or default_shapes_path())
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"[resonexuz] Configurador web en {url} (Ctrl+C para salir)", flush=True)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        srv.server_close()
    return 0
