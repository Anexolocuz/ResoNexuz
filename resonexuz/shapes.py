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


def build_3d_mesh(kind: str, level: dict[str, Any], guide_inner: float, guide_outer: float, t: float = 0.0
                  ) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, int, int]], np.ndarray]:
    rng = np.random.default_rng(19)
    dirs = rng.normal(size=(22, 3))
    dirs /= np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-6)
    aura = dirs * rng.uniform(0.76, 0.94, size=(22, 1))

    if kind == "sphere":
        v, e, tris = _icosphere_mesh(0.72)
        return v, e, tris, aura
    if kind == "atom":
        v, e, tris, electrons = _atom_mesh(t)
        return v, e, tris, np.vstack([electrons, aura * 0.92])
    if kind == "cube":
        v = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                      [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=np.float64) * 0.46
        e = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        tris = [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
                (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (0, 3, 7), (0, 7, 4)]
        return v, e, tris, aura * 0.85
    if kind == "octahedron":
        v = np.array([[0, -1, 0], [0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]], dtype=np.float64) * 0.70
        e = [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (4, 3), (3, 5), (5, 2)]
        tris = [(1, 4, 2), (1, 2, 5), (1, 5, 3), (1, 3, 4), (0, 2, 4), (0, 5, 2), (0, 3, 5), (0, 4, 3)]
        return v, e, tris, aura * 0.88
    if kind == "pyramid":
        v = np.array([[0, 0.74, 0], [-0.56, -0.50, -0.56], [0.56, -0.50, -0.56],
                      [0.56, -0.50, 0.56], [-0.56, -0.50, 0.56]], dtype=np.float64)
        e = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1)]
        tris = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (1, 2, 3), (1, 3, 4)]
        return v, e, tris, aura * 0.86
    if kind == "prism":
        a = np.linspace(0, 2 * math.pi, 6, endpoint=False)
        top = np.column_stack([np.cos(a) * 0.56, np.full(6, 0.42), np.sin(a) * 0.56])
        bot = np.column_stack([np.cos(a) * 0.56, np.full(6, -0.42), np.sin(a) * 0.56])
        v = np.vstack([top, bot])
        e = [(i, (i + 1) % 6) for i in range(6)] + [(6 + i, 6 + (i + 1) % 6) for i in range(6)] + [(i, 6 + i) for i in range(6)]
        tris = []
        for i in range(6):
            ni = (i + 1) % 6
            tris.extend([(i, ni, 6 + ni), (i, 6 + ni, 6 + i)])
        for i in range(1, 5):
            tris.append((0, i, i + 1))
            tris.append((6, 6 + i, 6 + i + 1))
        return v, e, tris, aura * 0.86
    if kind == "torus":
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
        return np.asarray(verts, dtype=np.float64), edges, tris, aura * 0.90

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
    return v, edges, tris, aura * 0.86


def project_3d_plexus(
    level: dict[str, Any],
    t: float,
    guide_inner: float,
    guide_outer: float,
    spec_l: np.ndarray,
    spec_r: np.ndarray,
    scale: float,
    react: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Proyecta la malla 3D con reactividad estéreo en arrays de triángulos, líneas y nodos."""
    v_raw, edges, tris, aura = build_3d_mesh(level.get("shape_3d", "sphere"), level, guide_inner, guide_outer, t)
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

    def _transform(pts3: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rv = pts3 @ rot.T
        z_cam = 2.6
        persp = 1.9 / np.maximum(z_cam - rv[:, 2], 0.6)
        p2 = rv[:, :2] * persp[:, None]
        rad = np.hypot(p2[:, 0], p2[:, 1])
        max_r = float(np.max(rad)) if rad.size else 1.0
        if max_r > guide_outer:
            p2 = p2 * (guide_outer / max_r)
        y_norm = np.clip((p2[:, 1] / max(guide_outer, 0.2)) * 0.5 + 0.5, 0.0, 1.0)
        b_idx = np.clip((y_norm * 63.0).astype(int), 0, 63)
        side = np.clip((p2[:, 0] + 0.03) / 0.06, 0.0, 1.0)
        sp = spec_l[b_idx] * (1.0 - side) + spec_r[b_idx] * side
        p2_audio = p2 * (1.0 + sp[:, None] * 0.14 * react) * scale
        depth = np.clip((rv[:, 2] + 0.85) / 1.7, 0.05, 1.0)
        return p2_audio, depth, sp

    vp, vd, vs = _transform(v_raw)
    ap, ad, as_ = _transform(aura)

    tri_buf = np.empty((len(tris) * 3, 6), dtype=np.float32) if tris else np.empty((0, 6), dtype=np.float32)
    for k, (a, b, c) in enumerate(tris):
        for m, vi in enumerate((a, b, c)):
            tri_buf[k * 3 + m] = [vp[vi, 0], vp[vi, 1], vd[vi], vs[vi], 0.0, 1.0]

    edge_buf = np.empty((len(edges) * 2, 6), dtype=np.float32) if edges else np.empty((0, 6), dtype=np.float32)
    for k, (a, b) in enumerate(edges):
        edge_buf[k * 2] = [vp[a, 0], vp[a, 1], vd[a], vs[a], 1.0, 1.0]
        edge_buf[k * 2 + 1] = [vp[b, 0], vp[b, 1], vd[b], vs[b], 1.0, 1.0]

    n_main, n_aura = len(vp), len(ap)
    node_buf = np.empty((n_main + n_aura, 6), dtype=np.float32)
    node_buf[:n_main, 0:2] = vp
    node_buf[:n_main, 2] = vd
    node_buf[:n_main, 3] = vs
    node_buf[:n_main, 4] = 2.0
    node_buf[:n_main, 5] = 8.0 + vd * 8.0 + vs * 7.0

    is_atom = level.get("shape_3d") == "atom"
    node_buf[n_main:, 0:2] = ap
    node_buf[n_main:, 2] = ad
    node_buf[n_main:, 3] = as_
    node_buf[n_main:, 4] = 2.0
    sizes = 5.0 + ad * 5.0 + as_ * 4.0
    if is_atom and n_aura >= 6:
        sizes[:6] = 13.0 + as_[:6] * 7.0
    node_buf[n_main:, 5] = sizes

    return tri_buf, edge_buf, node_buf
