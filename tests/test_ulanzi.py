"""Tests for skills/ulanzi-deck/scripts/ulanzi.py that need neither Ulanzi Studio nor any installed app.

Run: uv run --with pillow python -m unittest discover -s tests -v
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "ulanzi-deck" / "scripts" / "ulanzi.py"
FIX = ROOT / "tests" / "fixtures"

spec = importlib.util.spec_from_file_location("ulanzi", SCRIPT)
ulanzi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ulanzi)


def make_config(root: Path):
    (root / "Config").mkdir(parents=True, exist_ok=True)
    (root / "Config" / "device_source.json").write_text(json.dumps({"Devices": [{"Model": "D200H", "Name": "Deck", "UUID": "dev"}]}))
    (root / "Config" / "setting_source.json").write_text(json.dumps({"Devices": [{"CurrentDevice": "dev", "CurrentProfile": "Fixture"}]}))


def write_layout(path: Path, keys: dict, page_id="p"):
    path.write_text(json.dumps({"profileName": "T", "pages": [{"id": page_id, "keys": keys}]}), encoding="utf-8")


def run_cli(*argv):
    """Run ulanzi.main() in-process; returns (exit_code, stdout + stderr)."""
    out = io.StringIO()
    code = 0
    old = sys.argv
    sys.argv = ["ulanzi.py", *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            ulanzi.main()
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.argv = old
    return code, out.getvalue()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_smoke_layout_renders_every_key_and_state(self):
        code, out = run_cli("build", "--layout", str(FIX / "smoke.layout.json"), "--out", str(self.tmp))
        self.assertEqual(code, 0, out)
        self.assertIn("VALIDATION OK", out)
        from PIL import Image
        main = self.tmp / "pages" / "main"
        # stream toggle and scene (momentary) both have 2 images per the OBS plugin manifest
        for f in ("k4_0.png", "k4_0_s1.png", "k0_1.png", "k0_1_s1.png", "k1_1.png"):
            self.assertTrue((main / f).is_file(), f)
            with Image.open(main / f) as im:
                self.assertEqual(im.size, (196, 196))
        self.assertTrue((self.tmp / "preview.png").is_file())

    def test_invalid_layout_reports_each_problem(self):
        code, out = run_cli("build", "--layout", str(FIX / "invalid.layout.json"), "--out", str(self.tmp))
        self.assertEqual(code, 2, out)
        for needle in ("3_2 is the mini screen", "5_0: key must be", "kind 'teleport'", "media must be one of",
                       "folder target 'missing'", "app needs 'app'"):
            self.assertIn(needle, out)

    def test_empty_layout_is_rejected(self):
        code, out = run_cli("build", "--layout", str(FIX / "empty.layout.json"), "--out", str(self.tmp))
        self.assertEqual(code, 2, out)
        self.assertIn("layout has no pages", out)

    def test_folder_only_layout_is_rejected(self):
        lay = self.tmp / "folders.json"
        lay.write_text(json.dumps({"profileName": "x", "pages": [{"id": "f", "folder": True, "keys": {}}]}))
        code, out = run_cli("build", "--layout", str(lay), "--out", str(self.tmp / "o"))
        self.assertEqual(code, 2, out)
        self.assertIn("at least one top-level page", out)

    def test_page_without_keys_gets_a_build_dir(self):
        lay = self.tmp / "blank.json"
        lay.write_text(json.dumps({"profileName": "x", "pages": [{"id": "p", "keys": {}}]}))
        code, out = run_cli("build", "--layout", str(lay), "--out", str(self.tmp / "o"))
        self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / "o" / "pages" / "p").is_dir())


class ExportRoundTripTests(unittest.TestCase):
    """export must keep parameters and every state image (Codex review, finding 1)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "UlanziDeck"
        page = self.data / "ProfilesV2" / "p1.ulanziProfile" / "Profiles" / "pg1"
        (page / "Images").mkdir(parents=True)
        from PIL import Image
        for n in ("a.png", "b.png", "c.png"):
            Image.new("RGBA", (196, 196), (255, 0, 0, 255)).save(page / "Images" / n)

        def vp(n):
            return {"Icon": "", "IconRel": f"Images/{n}", "Text": ""}

        actions = {
            "0_0": {"Action": "com.ulanzi.ulanzideck.obsstudio.scene", "ActionParam": {"SceneName": "BRB"},
                    "Name": "BRB", "Plugin": ulanzi.PLUGINS["obs"], "ViewParam": [vp("a.png"), vp("b.png")]},
            "1_0": {"Action": "com.ulanzi.ulanzideck.multiaction.thing", "ActionParam": {"x": 1},
                    "Name": "Multi", "Plugin": {"Name": "X", "UUID": "com.x", "Version": "1"},
                    "ViewParam": [vp("a.png"), vp("b.png"), vp("c.png")]},
            "2_0": {"Action": "com.ulanzi.ulanzideck.system.open", "ActionParam": {"Path": "notepad", "Icon": "Files/Notepad.png"},
                    "Name": "Notepad", "Plugin": ulanzi.PLUGINS["system"], "ViewParam": [dict(vp("c.png"), Text="My Notes")]},
        }
        (page / "manifest.json").write_text(json.dumps(
            {"Controllers": [{"Actions": {}, "Type": "Encoder"}, {"Actions": actions, "Type": "Keypad"}], "Icon": "", "Name": "P"}))
        (self.data / "ProfilesV2" / "p1.ulanziProfile" / "manifest.json").write_text(json.dumps(
            {"Device": {"Model": "D200H", "UUID": "dev"}, "Name": "Fixture", "Pages": {"Current": "pg1", "Pages": ["pg1"]}, "Version": 2}))
        make_config(self.data)
        os.environ["ULANZI_DECK_ROOT"] = str(self.data)

    def tearDown(self):
        os.environ.pop("ULANZI_DECK_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_params_and_states_survive_export_and_build(self):
        lay = self.tmp / "out" / "layout.json"
        code, out = run_cli("export", "--profile", "Fixture", "-o", str(lay), "--keep-paths")
        self.assertEqual(code, 0, out)
        keys = json.loads(lay.read_text(encoding="utf-8"))["pages"][0]["keys"]
        self.assertEqual(keys["0_0"]["kind"], "obs")
        self.assertEqual(keys["0_0"]["params"], {"SceneName": "BRB"})
        self.assertEqual(len(keys["0_0"]["images"]), 2)
        self.assertEqual(keys["1_0"]["kind"], "raw")
        self.assertEqual(keys["1_0"]["params"], {"x": 1})
        self.assertEqual(keys["1_0"]["states"], 3)
        self.assertEqual(len(keys["1_0"]["images"]), 3)
        self.assertEqual(keys["2_0"]["params"], {"Icon": "Files/Notepad.png"})  # unmapped field kept
        self.assertNotIn("Path", keys["2_0"].get("params", {}))
        self.assertEqual(keys["2_0"]["title"], "My Notes")  # app-drawn title survives the round trip
        # Rebuild: one file per state, ready for apply to write one ViewParam each.
        plan = ulanzi.build(lay, self.tmp / "build")
        specs = plan["pages"][0]["keys"]
        self.assertEqual(len(specs["0_0"]["files"]), 2)
        self.assertEqual(len(specs["1_0"]["files"]), 3)

    def test_non_grid_keypad_entries_are_ignored(self):
        # macOS folder pages store an "Icon" entry next to the keys in Keypad.Actions.
        m = self.data / "ProfilesV2" / "p1.ulanziProfile" / "Profiles" / "pg1" / "manifest.json"
        pm = json.loads(m.read_text())
        pm["Controllers"][1]["Actions"]["Icon"] = {}
        m.write_text(json.dumps(pm))
        code, out = run_cli("keymap", "--profile", "Fixture")
        self.assertEqual(code, 0, out)
        lay = self.tmp / "out" / "layout.json"
        code, out = run_cli("export", "--profile", "Fixture", "-o", str(lay))
        self.assertEqual(code, 0, out)
        self.assertNotIn("Icon", json.loads(lay.read_text(encoding="utf-8"))["pages"][0]["keys"])


class ValidationTests(unittest.TestCase):
    """Findings from the plugin-validator / skill-reviewer pass, each pinned by a test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, keys, page_id="p"):
        lay = self.tmp / "l.json"
        write_layout(lay, keys, page_id)
        return run_cli("build", "--layout", str(lay), "--out", str(self.tmp / "out"))

    def test_page_id_cannot_escape_out_dir(self):
        code, out = self.build({"0_0": {"kind": "back", "label": "x"}}, page_id="../../escaped")
        self.assertEqual(code, 2, out)
        self.assertIn("must use only letters", out)
        self.assertFalse((self.tmp / "escaped").exists())

    def test_colors(self):
        code, out = self.build({"0_0": {"kind": "back", "label": "x", "color": "#FFF"}})
        self.assertEqual(code, 0, out)
        code, out = self.build({"0_0": {"kind": "back", "label": "x", "color": "purple"}})
        self.assertEqual(code, 2, out)
        self.assertIn("must be '#RRGGBB'", out)

    def test_text_requires_text(self):
        code, out = self.build({"0_0": {"kind": "text", "label": "x"}})
        self.assertEqual(code, 2, out)
        self.assertIn("text needs 'text'", out)

    def test_icon_sources_are_checked(self):
        bad = self.tmp / "fake.png"
        bad.write_text("not an image")
        code, out = self.build({"0_0": {"kind": "back", "label": "x", "iconFile": str(bad)}})
        self.assertEqual(code, 2, out)
        self.assertIn("iconFile is not a readable image", out)
        code, out = self.build({"0_0": {"kind": "back", "label": "x", "iconUrl": "file:///etc/passwd"}})
        self.assertEqual(code, 2, out)
        self.assertIn("iconUrl must be an https", out)

    def test_report_flags_risky_keys(self):
        code, out = self.build({"0_0": {"kind": "text", "label": "Spotify", "text": "rm -rf ~", "enter": True},
                                "1_0": {"kind": "web", "label": "Docs", "url": "https://example.com"}})
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"! 0_0 Spotify\s+type 'rm -rf ~' \+ Enter")
        self.assertRegex(out, r"\n {5}1_0 Docs\s+open URL https://example.com")  # no '!' for a plain https link

    def test_desktop_entry_ignores_action_groups(self):
        text = ("[Desktop Entry]\nName=Firefox\nExec=firefox %u\nIcon=firefox\n\n"
                "[Desktop Action new-private-window]\nName=New Private Window\nExec=firefox --private-window\n")
        self.assertEqual(ulanzi.desktop_entry(text)["Name"], "Firefox")
        self.assertEqual(ulanzi.desktop_entry(text)["Exec"], "firefox %u")


class RestoreGuardTests(unittest.TestCase):
    def test_restore_refuses_the_live_folder(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "ProfilesV2").mkdir()
        make_config(tmp)
        os.environ["ULANZI_DECK_ROOT"] = str(tmp)
        try:
            code, out = run_cli("restore", "--backup", str(tmp))
            self.assertEqual(code, 1, out)
            self.assertIn("is the live data folder", out)
            self.assertTrue((tmp / "ProfilesV2").is_dir())
        finally:
            os.environ.pop("ULANZI_DECK_ROOT", None)
            shutil.rmtree(tmp, ignore_errors=True)


class GuardTests(unittest.TestCase):
    def test_override_is_unverified_off_windows(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "ProfilesV2").mkdir()
        make_config(tmp)
        os.environ["ULANZI_DECK_ROOT"] = str(tmp)
        saved = ulanzi.OS
        try:
            ulanzi.OS = "Darwin"
            root, verified = ulanzi.deck_root()
            self.assertEqual(root, tmp)
            self.assertFalse(verified, "macOS override must still require --force-unverified")
        finally:
            ulanzi.OS = saved
            os.environ.pop("ULANZI_DECK_ROOT", None)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_obs_state_table_matches_manifest_shape(self):
        self.assertEqual(ulanzi.OBS_STATES["replaybuffersave"], 2)
        self.assertEqual(ulanzi.OBS_STATES["mediasourcecontrol"], 4)
        self.assertEqual(ulanzi.OBS_STATES["audiomixer"], 1)


if __name__ == "__main__":
    unittest.main()
