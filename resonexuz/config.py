"""Gestión de configuración multiplataforma (TOML) y rutas de usuario."""
from __future__ import annotations

import copy
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    PKG_DIR = Path(sys._MEIPASS) / "resonexuz"
else:
    PKG_DIR = Path(__file__).resolve().parent

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "ultra": {
        "render_scale": 1.0,
        "constellation": "full",
        "glow": True,
        "dither": True,
        "echo_detail": True,
        "plexus_facets": True,
        "plexus_aura": True,
        "max_fps": 0,
        "idle_fps": 20,
    },
    "high": {
        "render_scale": 1.0,
        "constellation": "full",
        "glow": True,
        "dither": True,
        "echo_detail": True,
        "plexus_facets": True,
        "plexus_aura": True,
        "max_fps": 60,
        "idle_fps": 15,
    },
    "medium": {
        "render_scale": 0.75,
        "constellation": "dots",
        "glow": True,
        "dither": False,
        "echo_detail": True,
        "plexus_facets": True,
        "plexus_aura": False,
        "max_fps": 60,
        "idle_fps": 10,
    },
    "low": {
        "render_scale": 0.55,
        "constellation": "off",
        "glow": False,
        "dither": False,
        "echo_detail": True,
        "plexus_facets": False,
        "plexus_aura": False,
        "max_fps": 30,
        "idle_fps": 6,
    },
    "ultra_low": {
        "render_scale": 0.4,
        "constellation": "off",
        "glow": False,
        "dither": False,
        "echo_detail": False,
        "plexus_facets": False,
        "plexus_aura": False,
        "max_fps": 24,
        "idle_fps": 4,
    },
}

DEFAULTS: dict[str, dict[str, Any]] = {
    "audio": {
        "sensitivity": 1.0,
        "gamma": 0.7,
        "silence_rms": 1e-4,
        "silence_seconds": 0.0,
        "stereo_separation": 1.0,
    },
    "peaks": {"primary_ratio": 1.32, "secondary_ratio": 1.45},
    "color": {
        "harmony": "split_complementary",
        "hue_smoothing": 0.035,
        "history_seconds": 5.0,
        "short_seconds": 20.0,
        "mode_weight": 1.0,
        "short_influence": 0.25,
        "tempo_influence": 0.36,
        "tone_influence": 0.16,
    },
    "visual": {"ring_size": 1.0, "ring_reactivity": 1.0, "particle_density": 1.0},
    "display": {"monitor": 0},
    "wallpaper": {"fps": 60},
    "quality": {
        "preset": "high",
        **QUALITY_PRESETS["high"],
    },
}


def user_config_dir() -> Path:
    """Devuelve la carpeta de configuración según el sistema operativo."""
    override = os.environ.get("RESONEXUZ_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "ResoNexuz"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ResoNexuz"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".config") / "resonexuz"


def default_config_path() -> Path:
    return user_config_dir() / "config.toml"


def ensure_user_files() -> tuple[Path, Path]:
    """Crea config.toml y shapes.json iniciales en la carpeta del usuario si no existen."""
    cfg_dir = user_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.toml"
    shp_file = cfg_dir / "shapes.json"
    if not cfg_file.exists():
        cfg_file.write_text((PKG_DIR / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
    if not shp_file.exists():
        shp_file.write_text((PKG_DIR / "shapes.json").read_text(encoding="utf-8"), encoding="utf-8")
    return cfg_file, shp_file


def load_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Devuelve la configuración mezclando config.toml sobre los valores por defecto."""
    cfg = copy.deepcopy(DEFAULTS)
    path = path or default_config_path()
    if not path.exists():
        path = PKG_DIR / "config.toml"
    try:
        with open(path, "rb") as fh:
            user = tomllib.load(fh)
    except FileNotFoundError:
        return cfg
    except tomllib.TOMLDecodeError as exc:
        print(f"[resonexuz] config.toml inválido ({exc}); usando valores por defecto.")
        return cfg
    for section, values in user.items():
        if isinstance(values, dict) and section in cfg:
            if section == "quality":
                preset = values.get("preset")
                if isinstance(preset, str) and preset in QUALITY_PRESETS:
                    cfg["quality"].update(QUALITY_PRESETS[preset])
            cfg[section].update(values)
    return cfg


def validate_quality(raw_q: dict[str, Any], base_q: dict[str, Any] | None = None) -> dict[str, Any]:
    """Valida y normaliza la sección [quality] de config.toml."""
    import math

    out = copy.deepcopy(base_q if base_q is not None else DEFAULTS["quality"])
    if not isinstance(raw_q, dict):
        return out
    preset = str(raw_q.get("preset", out["preset"]))
    valid_presets = (*QUALITY_PRESETS.keys(), "custom")
    out["preset"] = preset if preset in valid_presets else "custom"
    if preset in QUALITY_PRESETS and len(raw_q) == 1:
        out.update(QUALITY_PRESETS[preset])
        return out

    try:
        rs = float(raw_q.get("render_scale", out["render_scale"]))
        if math.isfinite(rs):
            out["render_scale"] = round(max(0.35, min(1.0, rs)), 2)
    except (TypeError, ValueError):
        pass
    con = str(raw_q.get("constellation", out["constellation"]))
    out["constellation"] = con if con in ("off", "dots", "full") else out["constellation"]
    for bk in ("glow", "dither", "echo_detail", "plexus_facets", "plexus_aura"):
        if bk in raw_q:
            out[bk] = bool(raw_q[bk])
    try:
        mf = int(raw_q.get("max_fps", out["max_fps"]))
        out["max_fps"] = 0 if mf <= 0 else max(15, min(165, mf))
    except (TypeError, ValueError):
        pass
    try:
        out["idle_fps"] = max(2, min(60, int(raw_q.get("idle_fps", out["idle_fps"]))))
    except (TypeError, ValueError):
        pass
    return out


def serialize_toml(cfg: dict[str, dict[str, Any]]) -> str:
    a, pk, c, v, d, w = cfg["audio"], cfg["peaks"], cfg["color"], cfg["visual"], cfg["display"], cfg["wallpaper"]
    q = cfg.get("quality", DEFAULTS["quality"])
    return (
        "# Configuración de ResoNexuz (recarga automática en vivo).\n\n"
        "[audio]\n"
        f"sensitivity = {a['sensitivity']}\n"
        f"gamma = {a['gamma']}\n"
        f"silence_rms = {a['silence_rms']}\n"
        f"silence_seconds = {a['silence_seconds']}\n"
        f"stereo_separation = {a['stereo_separation']}\n\n"
        "[peaks]\n"
        f"primary_ratio = {pk['primary_ratio']}\n"
        f"secondary_ratio = {pk['secondary_ratio']}\n\n"
        "[color]\n"
        f"harmony = \"{c['harmony']}\"\n"
        f"history_seconds = {c['history_seconds']}\n"
        f"short_seconds = {c['short_seconds']}\n"
        f"mode_weight = {c['mode_weight']}\n"
        f"short_influence = {c['short_influence']}\n"
        f"tempo_influence = {c['tempo_influence']}\n"
        f"tone_influence = {c['tone_influence']}\n"
        f"hue_smoothing = {c['hue_smoothing']}\n\n"
        "[visual]\n"
        f"ring_size = {v['ring_size']}\n"
        f"ring_reactivity = {v['ring_reactivity']}\n"
        f"particle_density = {v['particle_density']}\n\n"
        "[display]\n"
        f"monitor = {d['monitor']}\n\n"
        "[wallpaper]\n"
        f"fps = {w['fps']}\n\n"
        "[quality]\n"
        f"preset = \"{q['preset']}\"\n"
        f"render_scale = {q['render_scale']}\n"
        f"constellation = \"{q['constellation']}\"\n"
        f"glow = {str(bool(q['glow'])).lower()}\n"
        f"dither = {str(bool(q['dither'])).lower()}\n"
        f"echo_detail = {str(bool(q['echo_detail'])).lower()}\n"
        f"plexus_facets = {str(bool(q['plexus_facets'])).lower()}\n"
        f"plexus_aura = {str(bool(q['plexus_aura'])).lower()}\n"
        f"max_fps = {int(q['max_fps'])}\n"
        f"idle_fps = {int(q['idle_fps'])}\n"
    )
