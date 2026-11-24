"""Dibujado del anillo, formas SDF 2D y malla 3D plexus de ResoNexuz con moderngl."""
from __future__ import annotations

import colorsys
import math
import struct
import zlib
from pathlib import Path

import moderngl
import numpy as np

from .audio_engine import Frame
from .config import DEFAULTS, PKG_DIR
from .shapes import SDF_SIZE, build_level_sdf, load_shapes, project_3d_plexus

HARMONY = {"split_complementary": 150.0 / 360.0, "triadic": 120.0 / 360.0}
COLOR_ROLE = {"base": 0, "opp1": 1, "opp2": 2}
MODE_ID = {"preset": 0, "custom": 0, "3d": 1}
CONSTELLATION_MODE = {"off": 0, "dots": 1, "full": 2}


def _hsv_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def _mix_rgb(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


class Renderer:
    def __init__(self, ctx: moderngl.Context, cfg: dict, shapes_cfg: dict | None = None) -> None:
        shaders = PKG_DIR / "shaders"
        self.ctx = ctx
        self.prog = ctx.program(
            vertex_shader=(shaders / "ncs_ring.vert").read_text(encoding="utf-8"),
            fragment_shader=(shaders / "ncs_ring.frag").read_text(encoding="utf-8"),
        )
        self.vao = ctx.vertex_array(self.prog, [])

        self.p3d_prog = ctx.program(
            vertex_shader=(shaders / "plexus3d.vert").read_text(encoding="utf-8"),
            fragment_shader=(shaders / "plexus3d.frag").read_text(encoding="utf-8"),
        )
        self.p3d_vbo = ctx.buffer(reserve=65536, dynamic=True)
        self.p3d_vao = ctx.vertex_array(
            self.p3d_prog,
            [(self.p3d_vbo, "2f 1f 1f 1f 1f", "in_pos", "in_depth", "in_spec", "in_kind", "in_size")],
        )

        self.blit_prog = ctx.program(
            vertex_shader=(shaders / "ncs_ring.vert").read_text(encoding="utf-8"),
            fragment_shader=(shaders / "blit.frag").read_text(encoding="utf-8"),
        )
        self.blit_vao = ctx.vertex_array(self.blit_prog, [])
        self._scale_tex: moderngl.Texture | None = None
        self._scale_fbo: moderngl.Framebuffer | None = None
        self._scale_size = (0, 0)

        zero_sdf = np.zeros((SDF_SIZE, SDF_SIZE, 4), dtype=np.float32).tobytes()
        self.sdf_textures: list[moderngl.Texture] = []
        for idx in range(3):
            tex = ctx.texture((SDF_SIZE, SDF_SIZE), 4, zero_sdf, dtype="f4")
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            tex.repeat_x = False
            tex.repeat_y = False
            tex.use(location=idx)
            self.sdf_textures.append(tex)
            self._set(f"u_sdf{idx}", idx)

        self.ring_size = 1.0
        self.reactivity = 1.0
        self.density = 1.0
        self.harmony = HARMONY["split_complementary"]
        self.render_scale = 1.0
        self.q_echo = True
        self.q_plexus_facets = True
        self.q_plexus_aura = True
        self.shapes_cfg: dict = {}
        self.update_config(cfg)
        self.update_shapes(shapes_cfg or load_shapes())

    def _set(self, name: str, value) -> None:
        if name in self.prog:
            self.prog[name].value = value

    def update_config(self, cfg: dict) -> None:
        vis = cfg["visual"]
        q = cfg.get("quality", DEFAULTS["quality"])
        self.harmony = HARMONY.get(str(cfg["color"]["harmony"]), HARMONY["split_complementary"])
        self.ring_size = float(vis["ring_size"])
        self.reactivity = float(vis["ring_reactivity"])
        self.density = float(vis["particle_density"])
        self.render_scale = max(0.35, min(1.0, float(q.get("render_scale", 1.0))))
        self.q_echo = bool(q.get("echo_detail", True))
        self.q_plexus_facets = bool(q.get("plexus_facets", True))
        self.q_plexus_aura = bool(q.get("plexus_aura", True))

        self._set("u_harmony", self.harmony)
        self._set("u_ring_size", self.ring_size)
        self._set("u_reactivity", self.reactivity)
        self._set("u_density", self.density)
        self._set("u_q_constellation", CONSTELLATION_MODE.get(str(q.get("constellation", "full")), 2))
        self._set("u_q_glow", 1 if q.get("glow", True) else 0)
        self._set("u_q_dither", 1 if q.get("dither", True) else 0)
        self._set("u_q_echo", 1 if self.q_echo else 0)

    def update_shapes(self, shapes_cfg: dict) -> None:
        self.shapes_cfg = shapes_cfg
        gi = float(shapes_cfg.get("guide_inner", 0.24))
        go = float(shapes_cfg.get("guide_outer", 0.88))
        self._set("u_guide_inner", gi)
        self._set("u_guide_outer", go)

        levels = shapes_cfg.get("levels", [])
        enabled, mode, scale, react = [], [], [], []
        echo_on, echo_amp, echo_off, echo_peak, echo_thr, color_role = [], [], [], [], [], []

        for idx in range(3):
            lvl = levels[idx] if idx < len(levels) else {}
            en = 1 if lvl.get("enabled", idx == 0) else 0
            m = MODE_ID.get(str(lvl.get("mode", "preset")), 0)
            enabled.append(en)
            mode.append(m)
            scale.append(float(lvl.get("scale", 0.26 + idx * 0.08)))
            react.append(float(lvl.get("reactivity", 1.0)))
            echo_on.append(1 if lvl.get("echo_enabled", idx < 2) else 0)
            echo_amp.append(float(lvl.get("echo_amp", 1.5)))
            echo_off.append(float(lvl.get("echo_offset", 0.03)))
            echo_peak.append(1 if lvl.get("echo_peak_only", True) else 0)
            echo_thr.append(float(lvl.get("echo_threshold", 0.62)))
            color_role.append(COLOR_ROLE.get(str(lvl.get("color_role", "base")), idx % 3))

            if m == 0 and en:
                sdf = build_level_sdf(lvl, gi, go, size=SDF_SIZE)
                self.sdf_textures[idx].write(sdf.tobytes())

        self._set("u_lvl_enabled", enabled)
        self._set("u_lvl_mode", mode)
        self._set("u_lvl_scale", scale)
        self._set("u_lvl_react", react)
        self._set("u_lvl_echo_on", echo_on)
        self._set("u_lvl_echo_amp", echo_amp)
        self._set("u_lvl_echo_off", echo_off)
        self._set("u_lvl_echo_peak", echo_peak)
        self._set("u_lvl_echo_thr", echo_thr)
        self._set("u_lvl_color", color_role)

    def _draw_plexus_batch(self, buf: np.ndarray, prim: int, color: tuple[float, float, float],
                           accent: tuple[float, float, float], alpha: float) -> None:
        if buf.size == 0:
            return
        raw = buf.tobytes()
        if len(raw) > self.p3d_vbo.size:
            self.p3d_vbo.orphan(len(raw))
        self.p3d_vbo.write(raw)
        self.p3d_prog["u_color"].value = color
        self.p3d_prog["u_accent"].value = accent
        self.p3d_prog["u_alpha"].value = alpha
        self.p3d_vao.render(prim, vertices=len(buf))

    def _draw_3d_levels(self, f: Frame, w: int, h: int, t: float) -> None:
        levels = self.shapes_cfg.get("levels", [])
        if not any(lvl.get("enabled") and lvl.get("mode") == "3d" for lvl in levels):
            return

        d = f.dyn
        calm = max(0.0, min(1.0, float(f.idle)))
        bass = d.bass_env * (1.0 - calm) + (0.30 + 0.25 * math.sin(t * 0.9)) * calm
        gray = (0.19, 0.20, 0.235)
        col_base = _mix_rgb(_hsv_rgb(d.base_hue, 0.82, 0.95), gray, calm)
        col_opp1 = _mix_rgb(_hsv_rgb(d.base_hue + 0.50, 0.92, 1.0), gray, calm)
        col_opp2 = _mix_rgb(_hsv_rgb(d.base_hue + self.harmony, 0.88, 1.0), gray, calm)
        palette = {"base": col_base, "opp1": col_opp1, "opp2": col_opp2}

        gi = float(self.shapes_cfg.get("guide_inner", 0.24))
        go = float(self.shapes_cfg.get("guide_outer", 0.88))

        self.ctx.enable(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
        self.p3d_prog["u_aspect"].value = float(w) / max(float(h), 1.0)
        self.p3d_prog["u_point_scale"].value = max(0.65, float(h) / 900.0)

        for idx, lvl in enumerate(levels[:3]):
            if not lvl.get("enabled") or lvl.get("mode") != "3d":
                continue
            scale = (float(lvl.get("scale", 0.26 + idx * 0.08)) + bass * 0.035) * self.ring_size
            react = float(lvl.get("reactivity", 1.0)) * self.reactivity
            base_c = palette.get(str(lvl.get("color_role", "base")), col_base)
            echo_c = col_opp2 if lvl.get("color_role") == "opp1" else col_opp1

            tri_buf, edge_buf, node_buf = ((), (), ())  # type: ignore[assignment]
            echo_bufs: tuple[np.ndarray, np.ndarray] | None = None
            echo_alpha = 0.0
            exp_s = scale
            echo_react = react
            if self.q_echo and lvl.get("echo_enabled", False):
                crest = min(1.0, float(max(f.spectrum.max(), d.peak_primary, d.peak_secondary)))
                if lvl.get("echo_peak_only", True):
                    thr = float(lvl.get("echo_threshold", 0.62))
                    lo, hi = max(0.05, thr - 0.15), min(1.0, thr + 0.05)
                    u = max(0.0, min(1.0, (crest - lo) / max(hi - lo, 1e-4)))
                    echo_alpha = (u * u * (3.0 - 2.0 * u)) * (1.0 - calm) * 0.72
                else:
                    echo_alpha = (0.45 + 0.30 * crest) * (1.0 - 0.45 * calm)
                if echo_alpha > 0.02:
                    exp_s = scale * (1.0 + float(lvl.get("echo_offset", 0.03)) * 2.2 + d.peak_primary * 0.12)
                    echo_react = react * float(lvl.get("echo_amp", 1.4))

            if echo_alpha > 0.02:
                (tri_buf, edge_buf, node_buf), echo_bufs = project_3d_plexus(
                    lvl, t, gi, go, f.spectrum_l, f.spectrum_r, scale, react,
                    include_tris=self.q_plexus_facets, include_aura=self.q_plexus_aura,
                    echo_scale=exp_s, echo_react=echo_react,
                )
            else:
                tri_buf, edge_buf, node_buf = project_3d_plexus(
                    lvl, t, gi, go, f.spectrum_l, f.spectrum_r, scale, react,
                    include_tris=self.q_plexus_facets, include_aura=self.q_plexus_aura,
                )

            if echo_bufs is not None:
                e_edge, e_node = echo_bufs
                self._draw_plexus_batch(e_edge, moderngl.LINES, echo_c, base_c, echo_alpha)
                self._draw_plexus_batch(e_node, moderngl.POINTS, echo_c, base_c, echo_alpha * 0.9)

            alpha_main = 1.0 - 0.45 * calm
            self._draw_plexus_batch(tri_buf, moderngl.TRIANGLES, base_c, col_opp2, alpha_main)
            self._draw_plexus_batch(edge_buf, moderngl.LINES, base_c, col_opp1, alpha_main)
            self._draw_plexus_batch(node_buf, moderngl.POINTS, base_c, col_opp2, alpha_main)

        self.ctx.disable(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)

    def _ensure_scale_fbo(self, sw: int, sh: int) -> moderngl.Framebuffer:
        if self._scale_fbo is not None and self._scale_size == (sw, sh):
            return self._scale_fbo
        if self._scale_fbo is not None:
            self._scale_fbo.release()
        if self._scale_tex is not None:
            self._scale_tex.release()
        tex = self.ctx.texture((sw, sh), 4)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex.repeat_x = False
        tex.repeat_y = False
        self._scale_tex = tex
        self._scale_fbo = self.ctx.framebuffer(color_attachments=[tex])
        self._scale_size = (sw, sh)
        return self._scale_fbo

    def draw(self, f: Frame, w: int, h: int, t: float) -> None:
        d = f.dyn
        calm = max(0.0, min(1.0, float(f.idle)))
        bass = d.bass_env * (1.0 - calm) + (0.30 + 0.25 * math.sin(t * 0.9)) * calm
        rot = t * 0.12 + bass * 0.25

        for idx, tex in enumerate(self.sdf_textures):
            tex.use(location=idx)

        self.ctx.disable(moderngl.BLEND)
        self._set("u_time", float(t))
        self._set("u_base_hue", float(d.base_hue))
        self._set("u_peak1", float(d.peak_primary))
        self._set("u_peak2", float(d.peak_secondary))
        self._set("u_bass", float(d.bass_env))
        self._set("u_idle", float(f.idle))
        self._set("u_balance", float(f.stereo_balance))
        self._set("u_const_rot", (math.cos(rot), math.sin(rot)))
        self._set("u_const_scale", (14.0 * self.density) * (1.0 - bass * 0.08))
        if "u_spectrum_l" in self.prog:
            self.prog["u_spectrum_l"].write(f.spectrum_l.astype("f4", copy=False).tobytes())
        if "u_spectrum_r" in self.prog:
            self.prog["u_spectrum_r"].write(f.spectrum_r.astype("f4", copy=False).tobytes())

        use_scaled = self.render_scale < 0.999 and w >= 64 and h >= 64
        if use_scaled:
            target_fbo = self.ctx.fbo
            sw = max(64, int(round(w * self.render_scale)))
            sh = max(64, int(round(h * self.render_scale)))
            scale_fbo = self._ensure_scale_fbo(sw, sh)
            scale_fbo.use()
            self.ctx.viewport = (0, 0, sw, sh)
            self._set("u_resolution", (float(sw), float(sh)))
            self.vao.render(moderngl.TRIANGLES, vertices=3)

            target_fbo.use()
            self.ctx.viewport = (0, 0, w, h)
            assert self._scale_tex is not None
            self._scale_tex.use(location=3)
            self.blit_prog["u_tex"].value = 3
            self.blit_prog["u_resolution"].value = (float(w), float(h))
            self.blit_vao.render(moderngl.TRIANGLES, vertices=3)
        else:
            self.ctx.viewport = (0, 0, w, h)
            self._set("u_resolution", (float(w), float(h)))
            self.vao.render(moderngl.TRIANGLES, vertices=3)

        self._draw_3d_levels(f, w, h, t)

    def release(self) -> None:
        for tex in self.sdf_textures:
            tex.release()
        if self._scale_fbo is not None:
            self._scale_fbo.release()
        if self._scale_tex is not None:
            self._scale_tex.release()
        self.blit_vao.release()
        self.blit_prog.release()
        self.vao.release()
        self.prog.release()
        self.p3d_vao.release()
        self.p3d_vbo.release()
        self.p3d_prog.release()


def write_png(path: Path, rgb: bytes, w: int, h: int) -> None:
    rows = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h - 1, -1, -1))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))
    path.write_bytes(png)
