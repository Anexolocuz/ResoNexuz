"""Formas simétricas 2D, campos de distancia (SDF) y mallas 3D estilo plexus para ResoNexuz."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .config import PKG_DIR, user_config_dir

SDF_SIZE = 192
SDF_EXTENT = 1.25

PRESETS_2D: tuple[str, ...] = (
    "circle",
    "rounded_square",
    "triangle",
    "diamond",
    "hexagon",
    "star",
    "heart",
    "butterfly",
    "wave",
)

SHAPES_3D: tuple[str, ...] = (
    "sphere",
    "atom",
    "octahedron",
    "cube",
    "pyramid",
    "prism",
    "torus",
    "custom_spin",
)


def default_shapes_path() -> Path:
    return user_config_dir() / "shapes.json"


def _default_shapes() -> dict[str, Any]:
    return json.loads((PKG_DIR / "shapes.json").read_text(encoding="utf-8"))


def _merge_level(default_lvl: dict[str, Any], user_lvl: dict[str, Any]) -> dict[str, Any]:
    out = dict(default_lvl)
    for k, v in user_lvl.items():
        if k in out:
            out[k] = v
    out["id"] = int(out["id"])
    out["enabled"] = bool(out["enabled"])
    if out["mode"] not in ("preset", "custom", "3d"):
        out["mode"] = "preset"
    if out["preset"] not in PRESETS_2D:
        out["preset"] = "circle"
    if out["shape_3d"] not in SHAPES_3D:
        out["shape_3d"] = "sphere"
    if out["rot_axis"] not in ("y", "xy", "xyz"):
        out["rot_axis"] = "y"
    out["rot_dir"] = -1 if int(out["rot_dir"]) < 0 else 1
    out["rot_speed"] = float(np.clip(float(out["rot_speed"]), 0.0, 5.0))
    out["scale"] = float(np.clip(float(out["scale"]), 0.12, 0.70))
    out["reactivity"] = float(np.clip(float(out["reactivity"]), 0.0, 3.0))
    out["echo_enabled"] = bool(out["echo_enabled"])
    out["echo_amp"] = float(np.clip(float(out["echo_amp"]), 0.2, 3.0))
    out["echo_offset"] = float(np.clip(float(out["echo_offset"]), 0.005, 0.15))
    out["echo_peak_only"] = bool(out["echo_peak_only"])
    out["echo_threshold"] = float(np.clip(float(out["echo_threshold"]), 0.15, 0.95))
    out["closed"] = bool(out["closed"])
    if out["color_role"] not in ("base", "opp1", "opp2"):
        out["color_role"] = "base"
    pts = []
    for p in out.get("custom_points") or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append([float(np.clip(float(p[0]), 0.0, 1.0)), float(np.clip(float(p[1]), -1.0, 1.0))])
    out["custom_points"] = pts
    return out


def load_shapes(path: Path | None = None) -> dict[str, Any]:
    """Carga shapes.json mezclándolo con la estructura por defecto."""
    cfg = _default_shapes()
    path = path or default_shapes_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return cfg
    if isinstance(raw, dict):
        gi = float(raw.get("guide_inner", cfg["guide_inner"]))
        go = float(raw.get("guide_outer", cfg["guide_outer"]))
        cfg["guide_inner"] = float(np.clip(gi, 0.08, 0.55))
        cfg["guide_outer"] = float(np.clip(go, cfg["guide_inner"] + 0.12, 0.96))
        user_levels = raw.get("levels")
        if isinstance(user_levels, list):
            merged = []
            for idx, dflt in enumerate(cfg["levels"]):
                ul = user_levels[idx] if idx < len(user_levels) and isinstance(user_levels[idx], dict) else {}
                merged.append(_merge_level(dflt, ul))
            cfg["levels"] = merged
    return cfg


def preset_half_points(name: str, n: int = 64) -> tuple[np.ndarray, bool]:
    """Devuelve puntos de la mitad derecha (x >= 0, de abajo a arriba) y si la forma es cerrada."""
    t = np.linspace(0.0, 1.0, n)
    ang = t * math.pi

    if name == "rounded_square":
        s = np.sin(ang)
        c = -np.cos(ang)
        p = 5.0
        denom = (np.abs(s) ** p + np.abs(c) ** p) ** (1.0 / p)
        x = (s / np.maximum(denom, 1e-6)) * 0.72
        y = (c / np.maximum(denom, 1e-6)) * 0.72
        return np.column_stack([x, y]), True

    if name == "triangle":
        verts = np.array([[0.0, -0.68], [0.76, 0.56], [0.0, 0.56]])
        return _resample_polyline(verts, n), True

    if name == "diamond":
        verts = np.array([[0.0, -0.78], [0.68, 0.0], [0.0, 0.78]])
        return _resample_polyline(verts, n), True

    if name == "hexagon":
        a = np.array([0.0, 60.0, 120.0, 180.0]) * (math.pi / 180.0)
        verts = np.column_stack([np.sin(a) * 0.74, -np.cos(a) * 0.74])
        return _resample_polyline(verts, n), True

    if name == "star":
        half_angles = np.linspace(0.0, math.pi, 6)
        radii = np.array([0.40, 0.78, 0.40, 0.78, 0.40, 0.78])
        verts = np.column_stack([np.sin(half_angles) * radii, -np.cos(half_angles) * radii])
        return _resample_polyline(verts, n), True

    if name == "heart":
        tau = np.linspace(math.pi, 0.0, n)
        x = 16.0 * (np.sin(tau) ** 3)
        y = 13.0 * np.cos(tau) - 5.0 * np.cos(2 * tau) - 2.0 * np.cos(3 * tau) - np.cos(4 * tau)
        pts = np.column_stack([np.maximum(x, 0.0), y]) / 21.0
        pts[0, 0] = 0.0
        pts[-1, 0] = 0.0
        return pts, True

    if name == "butterfly":
        r = 0.56 * (0.62 + 0.34 * np.sin(2.0 * ang) + 0.14 * np.cos(4.0 * ang))
        x = np.sin(ang) * r
        y = -np.cos(ang) * r
        x[0] = 0.0
        x[-1] = 0.0
        return np.column_stack([x, y]), True

    if name == "wave":
        x = np.linspace(0.0, 0.80, n)
        y = 0.22 * np.sin(x * math.pi * 2.2) - 0.05
        return np.column_stack([x, y]), False

    x = np.sin(ang) * 0.65
    y = -np.cos(ang) * 0.65
    x[0] = 0.0
    x[-1] = 0.0
    return np.column_stack([x, y]), True


def _resample_polyline(pts: np.ndarray, n: int) -> np.ndarray:
    if len(pts) < 2:
        return np.repeat(pts[:1], n, axis=0) if len(pts) else np.zeros((n, 2))
    diffs = np.diff(pts, axis=0)
    seglen = np.hypot(diffs[:, 0], diffs[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seglen)])
    total = cum[-1]
    if total < 1e-6:
        return np.repeat(pts[:1], n, axis=0)
    target = np.linspace(0.0, total, n)
    x = np.interp(target, cum, pts[:, 0])
    y = np.interp(target, cum, pts[:, 1])
    return np.column_stack([x, y])


def clamp_to_guides(pts: np.ndarray, r_min: float, r_max: float) -> np.ndarray:
    """Acota cada punto entre las dos circunferencias guía (r_min <= r <= r_max)."""
    r = np.hypot(pts[:, 0], pts[:, 1])
    safe_r = np.maximum(r, 1e-5)
    clamped = np.clip(r, r_min, r_max)
    scale = np.where(r > 1e-5, clamped / safe_r, 1.0)
    out = pts * scale[:, None]
    zero_mask = r <= 1e-5
    if np.any(zero_mask):
        out[zero_mask] = [0.0, -r_min]
    return out


def level_half_contour(level: dict[str, Any], guide_inner: float, guide_outer: float, n: int = 56) -> tuple[np.ndarray, bool]:
    """Obtiene la mitad derecha normalizada y acotada entre las guías para un nivel."""
    if level["mode"] == "custom" and len(level.get("custom_points") or []) >= 2:
        raw = np.asarray(level["custom_points"], dtype=np.float64)
        raw[:, 0] = np.maximum(raw[:, 0], 0.0)
        closed = bool(level.get("closed", True))
        if closed:
            raw[0, 0] = 0.0
            raw[-1, 0] = 0.0
        pts = _resample_polyline(raw, n)
        return clamp_to_guides(pts, guide_inner, guide_outer), closed
    pts, closed = preset_half_points(level.get("preset", "circle"), n)
    return clamp_to_guides(pts, guide_inner, guide_outer), closed


def _point_in_poly_half(gx: np.ndarray, gy: np.ndarray, poly: np.ndarray) -> np.ndarray:
    inside = np.zeros(gx.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = (y1 > gy) != (y2 > gy)
        x_int = x1 + (gy - y1) * (x2 - x1) / (y2 - y1 + 1e-12)
        inside ^= cond & (gx < x_int)
    return inside


def build_level_sdf(level: dict[str, Any], guide_inner: float, guide_outer: float,
                    size: int = SDF_SIZE, extent: float = SDF_EXTENT) -> np.ndarray:
    """Genera textura RGBA float32 (size x size x 4): (sd, t_spec, inside, is_closed)."""
    half, closed = level_half_contour(level, guide_inner, guide_outer, n=52)
    left = np.column_stack([-half[-2:0:-1, 0], half[-2:0:-1, 1]]) if len(half) > 2 else np.empty((0, 2))
    full_poly = np.vstack([half, left]) if closed else half

    half_w = size // 2
    xs = np.linspace(0.0, extent, half_w, dtype=np.float64) + (extent / size)
    ys = np.linspace(-extent, extent, size, dtype=np.float64)
    gx, gy = np.meshgrid(xs, ys)

    a = half[:-1]
    b = half[1:]
    ba = b - a
    ba_len2 = np.maximum(np.sum(ba * ba, axis=1), 1e-10)

    px = gx[..., None]
    py = gy[..., None]
    ax = a[:, 0][None, None, :]
    ay = a[:, 1][None, None, :]
    bax = ba[:, 0][None, None, :]
    bay = ba[:, 1][None, None, :]

    proj = np.clip(((px - ax) * bax + (py - ay) * bay) / ba_len2[None, None, :], 0.0, 1.0)
    dx = px - (ax + bax * proj)
    dy = py - (ay + bay * proj)
    d2 = dx * dx + dy * dy
    idx = np.argmin(d2, axis=2)
    dist_r = np.sqrt(np.take_along_axis(d2, idx[..., None], axis=2)[..., 0])

    proj_win = np.take_along_axis(proj, idx[..., None], axis=2)[..., 0]
    step = 1.0 / max(len(a), 1)
    t_r = np.clip((idx.astype(np.float64) + proj_win) * step, 0.0, 1.0)

    if closed and len(full_poly) >= 3:
        in_r = _point_in_poly_half(gx, gy, full_poly).astype(np.float32)
        sd_r = np.where(in_r > 0.5, -dist_r, dist_r).astype(np.float32)
    else:
        in_r = np.zeros_like(dist_r, dtype=np.float32)
        sd_r = dist_r.astype(np.float32)

    out_r = np.stack([sd_r, t_r.astype(np.float32), in_r, np.full_like(sd_r, 1.0 if closed else 0.0)], axis=-1)
    out_l = out_r[:, ::-1, :]
    return np.concatenate([out_l, out_r], axis=1).astype(np.float32)


def _icosphere_mesh(radius: float = 0.72) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, int, int]]]:
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    base_v = [
        [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
        [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
        [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
    ]
    verts = [np.asarray(p, dtype=np.float64) / np.linalg.norm(p) for p in base_v]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    mid_cache: dict[tuple[int, int], int] = {}

    def midpoint(i: int, j: int) -> int:
        key = (min(i, j), max(i, j))
        if key in mid_cache:
            return mid_cache[key]
        m = 0.5 * (verts[i] + verts[j])
        m /= np.linalg.norm(m)
        idx = len(verts)
        verts.append(m)
        mid_cache[key] = idx
        return idx

    tris: list[tuple[int, int, int]] = []
    for a, b, c in faces:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        tris.extend([(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)])

    edge_set = set()
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            edge_set.add((min(u, v), max(u, v)))

    rng = np.random.default_rng(7)
    arr = np.asarray(verts, dtype=np.float64)
    arr = arr + rng.normal(0.0, 0.035, size=arr.shape)
    arr /= np.linalg.norm(arr, axis=1, keepdims=True)
    return arr * radius, sorted(edge_set), tris


def _atom_mesh(t: float) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, int, int]], np.ndarray]:
    nuc_v = np.array([[0, -1, 0], [0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float64) * 0.16
    edges: list[tuple[int, int]] = [
        (0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (4, 3), (3, 5), (5, 2)
    ]
    tris: list[tuple[int, int, int]] = [
        (1, 4, 2), (1, 2, 5), (1, 5, 3), (1, 3, 4),
        (0, 2, 4), (0, 5, 2), (0, 3, 5), (0, 4, 3),
    ]
    verts_list = [nuc_v]
    ring_n = 28
    ring_r = 0.72
    tilts = [(0.35, 0.0, 0.0), (0.35, 0.0, math.pi / 3.0), (0.35, 0.0, -math.pi / 3.0)]
    electrons = []
    for ri, (tx, _ty, tz) in enumerate(tilts):
        base_idx = sum(len(v) for v in verts_list)
        a = np.linspace(0, 2 * math.pi, ring_n, endpoint=False)
        ring = np.column_stack([np.cos(a) * ring_r, np.sin(a) * ring_r * 0.44, np.zeros(ring_n)])
        cx, sx = math.cos(tx), math.sin(tx)
        cz, sz = math.cos(tz), math.sin(tz)
        rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        mat = rz @ rx
        verts_list.append(ring @ mat.T)
        for i in range(ring_n):
            edges.append((base_idx + i, base_idx + ((i + 1) % ring_n)))
        for k in range(2):
            ang_e = t * (1.8 + ri * 0.25) + k * math.pi + ri * 1.1
            electrons.append(np.array([math.cos(ang_e) * ring_r, np.sin(ang_e) * ring_r * 0.44, 0.0]) @ mat.T)

    return np.vstack(verts_list), edges, tris, np.asarray(electrons, dtype=np.float64)


def _make_base_aura() -> np.ndarray:
    rng = np.random.default_rng(19)
    dirs = rng.normal(size=(22, 3))
    dirs /= np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-6)
    return dirs * rng.uniform(0.76, 0.94, size=(22, 1))


_BASE_AURA = _make_base_aura()
_STATIC_3D_CACHE: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_CUSTOM_3D_CACHE: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_ATOM_TILTS = ((0.35, 0.0, 0.0), (0.35, 0.0, math.pi / 3.0), (0.35, 0.0, -math.pi / 3.0))


def _atom_static_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray]]:
    cached = _STATIC_3D_CACHE.get("_atom_full")
    if cached is not None:
        return cached[0], cached[1], cached[2], _STATIC_3D_CACHE["_atom_mats"]  # type: ignore[return-value]

    nuc_v = np.array([[0, -1, 0], [0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float64) * 0.16
    edges: list[tuple[int, int]] = [
        (0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (4, 3), (3, 5), (5, 2)
    ]
    tris: list[tuple[int, int, int]] = [
        (1, 4, 2), (1, 2, 5), (1, 5, 3), (1, 3, 4),
        (0, 2, 4), (0, 5, 2), (0, 3, 5), (0, 4, 3),
    ]
    verts_list = [nuc_v]
    mats: list[np.ndarray] = []
    ring_n = 28
    ring_r = 0.72
    a = np.linspace(0, 2 * math.pi, ring_n, endpoint=False)
    base_ring = np.column_stack([np.cos(a) * ring_r, np.sin(a) * ring_r * 0.44, np.zeros(ring_n)])
    for tx, _ty, tz in _ATOM_TILTS:
        base_idx = sum(len(v) for v in verts_list)
        cx, sx = math.cos(tx), math.sin(tx)
        cz, sz = math.cos(tz), math.sin(tz)
        rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        mat = rz @ rx
        mats.append(mat)
        verts_list.append(base_ring @ mat.T)
        for i in range(ring_n):
            edges.append((base_idx + i, base_idx + ((i + 1) % ring_n)))

    v_arr = np.vstack(verts_list)
    e_arr = np.asarray(edges, dtype=np.int32)
    t_arr = np.asarray(tris, dtype=np.int32)
    _STATIC_3D_CACHE["_atom_full"] = (v_arr, e_arr, t_arr)
    _STATIC_3D_CACHE["_atom_mats"] = mats  # type: ignore[assignment]
    return v_arr, e_arr, t_arr, mats


def _atom_electrons(t: float, mats: list[np.ndarray]) -> np.ndarray:
    ring_r = 0.72
    pts = np.empty((6, 3), dtype=np.float64)
    idx = 0
    for ri, mat in enumerate(mats):
        speed = 1.8 + ri * 0.25
        for k in range(2):
            ang_e = t * speed + k * math.pi + ri * 1.1
            pts[idx] = np.array([math.cos(ang_e) * ring_r, math.sin(ang_e) * ring_r * 0.44, 0.0]) @ mat.T
            idx += 1
    return pts


def _get_static_3d(kind: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cached = _STATIC_3D_CACHE.get(kind)
    if cached is not None:
        return cached

    if kind == "sphere":
        v, edges, tris = _icosphere_mesh(0.72)
    elif kind == "cube":
        v = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                      [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=np.float64) * 0.46
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        tris = [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
                (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (0, 3, 7), (0, 7, 4)]
    elif kind == "octahedron":
        v = np.array([[0, -1, 0], [0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float64) * 0.70
        edges = [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (4, 3), (3, 5), (5, 2)]
        tris = [(1, 4, 2), (1, 2, 5), (1, 5, 3), (1, 3, 4), (0, 2, 4), (0, 5, 2), (0, 3, 5), (0, 4, 3)]
    elif kind == "pyramid":
        v = np.array([[0, 0.74, 0], [-0.56, -0.50, -0.56], [0.56, -0.50, -0.56],
                      [0.56, -0.50, 0.56], [-0.56, -0.50, 0.56]], dtype=np.float64)
        edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1)]
        tris = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (1, 2, 3), (1, 3, 4)]
    elif kind == "prism":
        a = np.linspace(0, 2 * math.pi, 6, endpoint=False)
        top = np.column_stack([np.cos(a) * 0.56, np.full(6, 0.42), np.sin(a) * 0.56])
        bot = np.column_stack([np.cos(a) * 0.56, np.full(6, -0.42), np.sin(a) * 0.56])
        v = np.vstack([top, bot])
        edges = [(i, (i + 1) % 6) for i in range(6)] + [(6 + i, 6 + (i + 1) % 6) for i in range(6)] + [(i, 6 + i) for i in range(6)]
        tris = []
        for i in range(6):
            ni = (i + 1) % 6
            tris.extend([(i, ni, 6 + ni), (i, 6 + ni, 6 + i)])
        for i in range(1, 5):
            tris.append((0, i, i + 1))
            tris.append((6, 6 + i, 6 + i + 1))
    else:  # torus
        maj, min_n = 12, 6
        R, r = 0.54, 0.20
        verts, edges, tris = [], [], []
        for i in range(maj):
            u = 2 * math.pi * i / maj
            for j in range(min_n):
                w = 2 * math.pi * j / min_n
                verts.append([(R + r * math.cos(w)) * math.cos(u), r * math.sin(w), (R + r * math.cos(w)) * math.sin(u)])
                cur = i * min_n + j
                nu = ((i + 1) % maj) * min_n + j
                nw = i * min_n + ((j + 1) % min_n)
                nuw = ((i + 1) % maj) * min_n + ((j + 1) % min_n)
                edges.append((cur, nu))
                edges.append((cur, nw))
                tris.extend([(cur, nu, nuw), (cur, nuw, nw)])
        v = np.asarray(verts, dtype=np.float64)

    res = (
        np.asarray(v, dtype=np.float64),
        np.asarray(edges, dtype=np.int32).reshape(-1, 2),
        np.asarray(tris, dtype=np.int32).reshape(-1, 3),
    )
    _STATIC_3D_CACHE[kind] = res
    return res


def _get_custom_spin_3d(level: dict[str, Any], guide_inner: float, guide_outer: float
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pts_key = tuple((round(float(p[0]), 4), round(float(p[1]), 4)) for p in (level.get("custom_points") or []))
    key = (round(guide_inner, 4), round(guide_outer, 4), bool(level.get("closed", True)),
           str(level.get("mode", "preset")), str(level.get("preset", "circle")), pts_key)
    cached = _CUSTOM_3D_CACHE.get(key)
    if cached is not None:
        return cached

    half, closed = level_half_contour(level, guide_inner, guide_outer, n=14)
    left = np.column_stack([-half[-2:0:-1, 0], half[-2:0:-1, 1]])
    poly = np.vstack([half, left]) if closed else half
    m = len(poly)
    front = np.column_stack([poly[:, 0], poly[:, 1], np.full(m, 0.18)])
    back = np.column_stack([poly[:, 0], poly[:, 1], np.full(m, -0.18)])
    v = np.vstack([front, back])
    edges, tris = [], []
    limit = m if closed else m - 1
    for i in range(limit):
        ni = (i + 1) % m
        edges.extend([(i, ni), (m + i, m + ni), (i, m + i)])
        tris.extend([(i, ni, m + ni), (i, m + ni, m + i)])
    res = (
        v,
        np.asarray(edges, dtype=np.int32).reshape(-1, 2),
        np.asarray(tris, dtype=np.int32).reshape(-1, 3),
    )
    if len(_CUSTOM_3D_CACHE) > 24:
        _CUSTOM_3D_CACHE.clear()
    _CUSTOM_3D_CACHE[key] = res
    return res


_AURA_SCALE = {
    "sphere": 1.0,
    "atom": 0.92,
    "cube": 0.85,
    "octahedron": 0.88,
    "pyramid": 0.86,
    "prism": 0.86,
    "torus": 0.90,
}


def build_3d_mesh(kind: str, level: dict[str, Any], guide_inner: float, guide_outer: float, t: float = 0.0,
                  include_aura: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    aura = _BASE_AURA * _AURA_SCALE.get(kind, 0.86) if include_aura else np.empty((0, 3), dtype=np.float64)
    if kind == "atom":
        v, e, tris, mats = _atom_static_data()
        electrons = _atom_electrons(t, mats)
        extra = np.vstack([electrons, aura]) if include_aura else electrons
        return v, e, tris, extra
    if kind in ("sphere", "cube", "octahedron", "pyramid", "prism", "torus"):
        v, e, tris = _get_static_3d(kind)
        return v, e, tris, aura
    v, e, tris = _get_custom_spin_3d(level, guide_inner, guide_outer)
    return v, e, tris, aura


def _pack_plexus_buffers(
    vp: np.ndarray,
    vd: np.ndarray,
    vs: np.ndarray,
    ap: np.ndarray,
    ad: np.ndarray,
    as_: np.ndarray,
    edge_idx: np.ndarray,
    tri_idx: np.ndarray,
    is_atom: bool,
    include_tris: bool,
    include_aura: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_main = len(vp)
    n_aura = len(ap)
    base_v = np.empty((n_main, 6), dtype=np.float32)
    base_v[:, 0:2] = vp
    base_v[:, 2] = vd
    base_v[:, 3] = vs
    base_v[:, 5] = 1.0

    if include_tris and len(tri_idx):
        base_v[:, 4] = 0.0
        tri_buf = base_v[tri_idx.ravel()]
    else:
        tri_buf = np.empty((0, 6), dtype=np.float32)

    if len(edge_idx):
        base_v[:, 4] = 1.0
        edge_buf = base_v[edge_idx.ravel()]
    else:
        edge_buf = np.empty((0, 6), dtype=np.float32)

    node_buf = np.empty((n_main + n_aura, 6), dtype=np.float32)
    node_buf[:n_main, 0:2] = vp
    node_buf[:n_main, 2] = vd
    node_buf[:n_main, 3] = vs
    node_buf[:n_main, 4] = 2.0
    node_buf[:n_main, 5] = 8.0 + vd * 8.0 + vs * 7.0

    if n_aura:
        node_buf[n_main:, 0:2] = ap
        node_buf[n_main:, 2] = ad
        node_buf[n_main:, 3] = as_
        node_buf[n_main:, 4] = 2.0
        sizes = 5.0 + ad * 5.0 + as_ * 4.0
        if is_atom:
            n_elec = min(6, n_aura)
            sizes[:n_elec] = 13.0 + as_[:n_elec] * 7.0
        node_buf[n_main:, 5] = sizes

    return tri_buf, edge_buf, node_buf


def project_3d_plexus(
    level: dict[str, Any],
    t: float,
    guide_inner: float,
    guide_outer: float,
    spec_l: np.ndarray,
    spec_r: np.ndarray,
    scale: float,
    react: float,
    include_tris: bool = True,
    include_aura: bool = True,
    echo_scale: float | None = None,
    echo_react: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | tuple[tuple[np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
    """Proyecta la malla 3D con reactividad estéreo (y eco opcional sin recalcular rotación)."""
    kind = level.get("shape_3d", "sphere")
    is_atom = kind == "atom"
    v_raw, edge_idx, tri_idx, aura = build_3d_mesh(kind, level, guide_inner, guide_outer, t, include_aura=include_aura)
    ang = t * float(level.get("rot_speed", 0.7)) * float(level.get("rot_dir", 1))
    axis = level.get("rot_axis", "y")

    ax_x = 0.28 if axis == "y" else ang * 0.65
    ax_y = ang
    ax_z = ang * 0.35 if axis == "xyz" else 0.0

    cx, sx = math.cos(ax_x), math.sin(ax_x)
    cy, sy = math.cos(ax_y), math.sin(ax_y)
    cz, sz = math.cos(ax_z), math.sin(ax_z)

    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    rot = rz @ rx @ ry

    def _transform_base(pts3: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if pts3.size == 0:
            z0 = np.empty((0, 2), dtype=np.float32)
            z1 = np.empty(0, dtype=np.float32)
            return z0, z1, z1
        rv = pts3 @ rot.T
        persp = 1.9 / np.maximum(2.6 - rv[:, 2], 0.6)
        p2 = rv[:, :2] * persp[:, None]
        rad = np.hypot(p2[:, 0], p2[:, 1])
        max_r = float(np.max(rad)) if rad.size else 1.0
        if max_r > guide_outer:
            p2 = p2 * (guide_outer / max_r)
        y_norm = np.clip((p2[:, 1] / max(guide_outer, 0.2)) * 0.5 + 0.5, 0.0, 1.0)
        b_idx = np.clip((y_norm * 63.0).astype(int), 0, 63)
        side = np.clip((p2[:, 0] + 0.03) / 0.06, 0.0, 1.0)
        sp = spec_l[b_idx] * (1.0 - side) + spec_r[b_idx] * side
        depth = np.clip((rv[:, 2] + 0.85) / 1.7, 0.05, 1.0)
        return p2, depth, sp

    vp_base, vd, vs = _transform_base(v_raw)
    ap_base, ad, as_ = _transform_base(aura)

    vp = vp_base * (1.0 + vs[:, None] * 0.14 * react) * scale
    ap = ap_base * (1.0 + as_[:, None] * 0.14 * react) * scale if len(ap_base) else ap_base
    main_bufs = _pack_plexus_buffers(
        vp, vd, vs, ap, ad, as_, edge_idx, tri_idx, is_atom, include_tris, include_aura
    )

    if echo_scale is not None and echo_react is not None:
        vp_e = vp_base * (1.0 + vs[:, None] * 0.14 * echo_react) * echo_scale
        ap_e = ap_base * (1.0 + as_[:, None] * 0.14 * echo_react) * echo_scale if len(ap_base) else ap_base
        _, e_edge, e_node = _pack_plexus_buffers(
            vp_e, vd, vs, ap_e, ad, as_, edge_idx, tri_idx, is_atom, False, include_aura
        )
        return main_bufs, (e_edge, e_node)

    return main_bufs
