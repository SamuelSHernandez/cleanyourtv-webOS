"""Themes: every folder is valid, has its real-TV screenshot, and themes/README.md matches the code."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import faketv  # noqa: F401

from cytv_webos import build, ipk, themes
from cytv_webos.errors import Refused

ROOT = Path(__file__).resolve().parents[1]


def folders():
    return sorted(p for p in themes.THEMES.iterdir() if p.is_dir())


class ThemeFoldersTest(unittest.TestCase):
    def test_every_theme_loads_and_has_a_real_tv_screenshot(self):
        self.assertTrue(folders())
        for folder in folders():
            t = themes.load(folder)
            shot = folder / "screenshot.jpg"
            self.assertTrue(shot.is_file(), f"{folder.name}: screenshot.jpg from a real TV is required")
            data = shot.read_bytes()
            self.assertTrue(data.startswith(b"\xff\xd8\xff"), f"{folder.name}: screenshot is not a JPEG")
            self.assertLessEqual(len(data), 300 * 1024, f"{folder.name}: screenshot over 300 KB")
            self.assertNotIn("theme/screenshot.jpg", t["files"], "screenshots are never packed")

    def test_readme_tables_are_generated(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_docs.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_default_theme_is_the_built_in_values(self):
        schema = themes.schema()
        cfg = json.loads((themes.THEMES / "default" / "config.json").read_text())
        for k, v in cfg.items():
            self.assertEqual(v, schema[k]["default"], f"default/config.json {k} differs from the launcher's default")

    def test_python_and_launcher_agree_on_every_default(self):
        for key, spec in themes.schema().items():
            self.assertTrue(themes.check(spec, spec["default"]) or spec["default"] is None, key)


class ThemeLoaderTest(unittest.TestCase):
    def folder(self, config, files=None):
        d = Path(tempfile.mkdtemp()) / "t"
        d.mkdir()
        (d / "config.json").write_text(json.dumps(config) if not isinstance(config, str) else config)
        for name, data in (files or {}).items():
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_bytes(data)
        return d

    def test_unknown_or_bad_keys_are_refused_at_build(self):
        for cfg in ({"colums": 4}, {"columns": 9}, {"background_color": "red"}, {"app_keys": ["13:netflix"]},
                    {"greeting_name": "a\u0007b"}, {"wallpaper_moods": {"noon": []}}, "[]", "{not json"):
            with self.assertRaises(Refused, msg=cfg):
                themes.load(self.folder(cfg))

    def test_pictures_are_checked_by_their_bytes(self):
        png = (themes.THEMES / "aurora" / "wallpaper.png").read_bytes()
        with self.assertRaises(Refused):
            themes.load(self.folder({}, {"wallpaper.jpg": png}))            # a PNG named .jpg
        with self.assertRaises(Refused):
            themes.load(self.folder({}, {"wallpaper.png": b"<script>x</script>"}))
        with self.assertRaises(Refused):
            themes.load(self.folder({}, {"wallpaper.png": png + b"0" * themes.MAX_PICTURE}))
        with self.assertRaises(Refused):
            themes.load(self.folder({}, {"style.css": b"body{}"}))
        with self.assertRaises(Refused):
            themes.load(self.folder({"wallpaper_moods": {"night": ["missing.jpg"]}}))
        t = themes.load(self.folder({}, {"wallpapers/001.png": png, "wallpapers/captions.txt": b"001.png\tDusk"}))
        self.assertEqual(t["wallpapers"]["files"], ["001.png"])

    def test_theme_script_cannot_break_out_of_its_script_tag(self):
        t = themes.load(self.folder({"greeting_name": "</script><script>alert(1)"}))
        self.assertNotIn("<", themes.script(t).split("\n", 1)[1])

    def test_a_theme_is_baked_into_the_package(self):
        out = Path(tempfile.mkdtemp())
        path, _, info = build.build(None, out, theme_dir=themes.THEMES / "aurora")
        members = dict(ipk.read_members(path.read_bytes()))
        import gzip, io, tarfile
        names = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"]))).getnames()
        app = f"./usr/palm/applications/{info['id']}/"
        self.assertIn(app + "theme/wallpaper.png", names)
        self.assertIn(app + "js/theme.js", names)
        self.assertNotIn(app + "theme/screenshot.jpg", names)
        self.assertNotIn(app + "theme/make_wallpaper.py", names)
        a, _, _ = build.build(None, Path(tempfile.mkdtemp()), theme_dir=themes.THEMES / "aurora")
        self.assertEqual(a.read_bytes(), path.read_bytes(), "a themed build is repeatable too")


if __name__ == "__main__":
    unittest.main()
