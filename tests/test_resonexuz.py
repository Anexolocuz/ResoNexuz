"""Pruebas unitarias e integración para ResoNexuz."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from resonexuz import audio_engine, config, shapes, web_ui


class TestResoNexuz(unittest.TestCase):
    def test_config_and_user_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("RESONEXUZ_CONFIG_DIR")
            os.environ["RESONEXUZ_CONFIG_DIR"] = td
            try:
                cfg_p, shp_p = config.ensure_user_files()
                self.assertTrue(cfg_p.is_file() and shp_p.is_file())
                cfg = config.load_config()
                self.assertEqual(cfg["audio"]["stereo_separation"], 1.0)
                shp = shapes.load_shapes()
                self.assertEqual(len(shp["levels"]), 3)
            finally:
                if old is None:
                    os.environ.pop("RESONEXUZ_CONFIG_DIR", None)
                else:
                    os.environ["RESONEXUZ_CONFIG_DIR"] = old

    def test_sdf_symmetry_and_3d_plexus(self) -> None:
        shp = shapes.load_shapes(config.PKG_DIR / "shapes.json")
        for preset in shapes.PRESETS_2D:
            lvl = dict(shp["levels"][0], mode="preset", preset=preset)
            sdf = shapes.build_level_sdf(lvl, shp["guide_inner"], shp["guide_outer"])
            self.assertEqual(sdf.shape, (shapes.SDF_SIZE, shapes.SDF_SIZE, 4))
            self.assertTrue(np.all(np.isfinite(sdf)))
            half = shapes.SDF_SIZE // 2
            self.assertTrue(np.allclose(sdf[:, :half, 0], sdf[:, half:, 0][:, ::-1], atol=1e-5))

        sp = np.full(64, 0.5, dtype=np.float32)
        for s3 in shapes.SHAPES_3D:
            lvl = dict(shp["levels"][0], mode="3d", shape_3d=s3)
            tri, edge, node = shapes.project_3d_plexus(lvl, 1.2, shp["guide_inner"], shp["guide_outer"], sp, sp, 0.35, 1.0)
            self.assertGreater(len(edge), 0)
            self.assertGreater(len(node), 0)
            self.assertTrue(np.all(np.isfinite(tri)) and np.all(np.isfinite(edge)) and np.all(np.isfinite(node)))

    def test_stereo_dsp(self) -> None:
        cfg = config.load_config(config.PKG_DIR / "config.toml")
        eng = audio_engine.AudioEngine(cfg)
        rng = np.random.default_rng(1)
        for i in range(6):
            eng.process_block(audio_engine.demo_block_stereo(i, rng))
        fr = eng.get_frame()
        self.assertEqual(fr.spectrum_l.shape, (64,))
        self.assertEqual(fr.spectrum_r.shape, (64,))
        self.assertLess(fr.idle, 1.0)

    def test_web_ui_roundtrip_and_csrf(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_p = Path(td) / "config.toml"
            shp_p = Path(td) / "shapes.json"
            srv = web_ui.make_server("127.0.0.1", 0, cfg_p, shp_p)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                    self.assertEqual(r.status, 200)
                    self.assertIn("ResoNexuz", r.read().decode())

                st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=3).read())
                st["shapes"]["levels"][0]["mode"] = "3d"
                st["shapes"]["levels"][0]["shape_3d"] = "atom"
                st["shapes"]["levels"][0]["echo_peak_only"] = True
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/config",
                    data=json.dumps({"config": st["config"], "shapes": st["shapes"]}).encode(),
                    headers={"Content-Type": "application/json", "X-ResoNexuz": "1"},
                    method="POST",
                )
                res = json.loads(urllib.request.urlopen(req, timeout=3).read())
                self.assertTrue(res["ok"])
                st2 = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=3).read())
                self.assertEqual(st2["shapes"]["levels"][0]["shape_3d"], "atom")

                req_no_hdr = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/config",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req_no_hdr, timeout=3)
                self.assertEqual(ctx.exception.code, 403)
                ctx.exception.close()
            finally:
                srv.shutdown()
                srv.server_close()

    def test_moderngl_render(self) -> None:
        import moderngl
        from resonexuz import renderer

        ctx = None
        for kw in ({"backend": "egl"}, {}):
            try:
                ctx = moderngl.create_standalone_context(**kw)
                break
            except Exception:
                continue
        if ctx is None:
            self.skipTest("Sin contexto OpenGL standalone en este entorno")

        cfg = config.load_config(config.PKG_DIR / "config.toml")
        shp = shapes.load_shapes(config.PKG_DIR / "shapes.json")
        shp["levels"][0]["mode"] = "3d"
        shp["levels"][0]["shape_3d"] = "sphere"
        shp["levels"][1]["mode"] = "3d"
        shp["levels"][1]["shape_3d"] = "atom"
        r = renderer.Renderer(ctx, cfg, shp)
        eng = audio_engine.AudioEngine(cfg)
        eng.process_block(audio_engine.demo_block_stereo(0, np.random.default_rng(1)))
        fbo = ctx.simple_framebuffer((320, 200))
        fbo.use()
        r.draw(eng.get_frame(), 320, 200, 1.0)
        rgb = np.frombuffer(fbo.read(components=3, alignment=1), dtype=np.uint8)
        self.assertGreater(int(rgb.max()), 150)
        r.release()
        fbo.release()
        ctx.release()


if __name__ == "__main__":
    unittest.main()
