"""Filesystem and IPC contract checks; no installed app or hardware is changed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import setup_mcdu as shared
from simapppro_v1 import Backend, IPC_API


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value), encoding="utf-8")


def font_config():
    return {"fontName": "WWT_MCDU", "newFontName": "WWT_MCDU", "version": "test",
            "largeFontConfig": {"fontId": 5, "pcFontSelected": "WWT_MCDU", "xScale": 1.2},
            "smallFontConfig": {"fontId": 6, "pcFontSelected": "WWT_MCDU", "yShift": 5},
            "pixelConfig": {}, "singleCharConfig": {"LA": {"pcFontSelected": "user-font"}}}


class Steps:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, fn, *args):
        import inspect
        return fn(*args, tick=lambda *args: None) if "tick" in inspect.signature(fn).parameters else fn(*args)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.exe = self.folder / "install" / "SimAppPro.exe"
        self.exe.parent.mkdir()
        self.exe.touch()
        self.api = SimpleNamespace(**{k: getattr(shared, k) for k in
            ["SetupError", "LAYOUT", "FONT_SLOT", "FENIX_COLOURS", "DEFAULT_Y", "Y_RANGE",
             "load_json", "save_json", "font_name", "fmt_offset", "y_of"]})
        self.api.HERE = str(self.folder)
        fonts = [self.folder / "fonts" / f"FMGC-Test-{s}.ttf" for s in ("Large", "Small")]
        for f in fonts:
            f.parent.mkdir(exist_ok=True)
            f.write_bytes(b"test project font")
        self.api.font_files = lambda: tuple(map(str, fonts))
        self.api.app_pids = Mock(return_value=set())
        self.api.is_admin = Mock(return_value=True)
        self.api.wait_for_mcdu = Mock(return_value="Captain")
        self.api.wait = Mock()
        self.backend = Backend(self.api, str(self.exe), str(self.folder / "profile"))
        self.b = self.backend
        self.cfg = {"layoutConfig": {"scX": 16, "scY": 17, "matrixW": 23, "matrixH": 29},
                    "fontConfig": {"fontSelected": "WWT_MCDU"},
                    "previewConfig": {"xBase": 36, "yBase": 20, "row": 14, "col": 24, "charArray": ["A"]},
                    "colorConfig": {"colorArray": [{"colorName": k, "currentColor": "#111111FF"}
                                                  for k in shared.FENIX_COLOURS]}}
        write(self.b.config, self.cfg)
        write(self.b.global_config, {"unrelated": {"keep": True}, "CDU_Config": {
            self.b.key: {"YAxisPoint": 37}, "PFP7Config": {"keep": "other device"}}})
        write(self.b.set_dir("WWT_MCDU") / "WWT_MCDU_config.json", font_config())
        self.b.stop = Mock()
        self.b.start = Mock()
        self.ui = Mock()
        self.ui.steps.side_effect = lambda plan: Steps()

    def test_patch_uses_dedicated_set_and_preserves_user_font(self):
        before = self.b.load(self.b.set_dir("WWT_MCDU") / "WWT_MCDU_config.json")
        self.b.preflight()
        self.b.prepare_patch(18)
        name, cfg, _ = self.b.selected()
        self.assertEqual(name, "FMGC-Test")
        font = self.b.load(cfg)
        self.assertEqual(font["singleCharConfig"], {})
        self.assertEqual(font["largeFontConfig"]["fontId"], 5)
        self.assertEqual(font["smallFontConfig"]["fontId"], 6)
        self.assertEqual(font["smallFontConfig"]["yShift"], 0)
        self.assertEqual(font["pixelConfig"]["scY"], 18)
        self.assertEqual(self.b.chosen_y(), 18)
        self.assertEqual(self.b.load(self.b.set_dir("WWT_MCDU") / "WWT_MCDU_config.json"), before)
        cfg = self.b.load(self.b.config)
        self.assertEqual(cfg["previewConfig"]["xBase"] + cfg["layoutConfig"]["scX"], 52)
        self.assertEqual(cfg["previewConfig"]["yBase"] + cfg["layoutConfig"]["scY"], 18)

    def test_unowned_name_collision_is_not_overwritten(self):
        folder = self.b.set_dir(self.b.set_name)
        folder.mkdir()
        (folder / "keep.txt").write_text("user data")
        with self.assertRaises(shared.SetupError):
            self.b.prepare_patch(20)
        self.assertEqual((folder / "keep.txt").read_text(), "user data")

    def test_backup_restore_preserves_unrelated_global_settings(self):
        backup = Path(self.b.backup())
        self.b.prepare_patch(18)
        current = self.b.load(self.b.global_config)
        current["unrelated"] = {"new": "keep this change"}
        current["CDU_Config"]["PFP7Config"] = {"new": "other device"}
        current["CDU_Config"][self.b.key] = {"YAxisPoint": 18}
        write(self.b.global_config, current)
        src, manifest = self.b.validate_backup(backup)
        self.b.put_back(src)
        self.b.restore_scope(manifest["scope"])
        restored = self.b.load(self.b.global_config)
        self.assertEqual(restored["CDU_Config"][self.b.key], {"YAxisPoint": 37})
        self.assertEqual(restored["unrelated"], current["unrelated"])
        self.assertEqual(restored["CDU_Config"]["PFP7Config"], current["CDU_Config"]["PFP7Config"])
        self.assertEqual(self.b.load(self.b.config), self.cfg)

    def test_absent_global_subtree_is_removed_without_losing_other_devices(self):
        self.b.restore_scope({"container_present": False, "present": False, "value": None})
        cfg = self.b.load(self.b.global_config)
        self.assertNotIn(self.b.key, cfg["CDU_Config"])
        self.assertIn("PFP7Config", cfg["CDU_Config"])
        write(self.b.global_config, {"unrelated": 123, "CDU_Config": {self.b.key: {}}})
        self.b.restore_scope({"container_present": False, "present": False, "value": None})
        self.assertEqual(self.b.load(self.b.global_config), {"unrelated": 123})

    def test_cross_backend_and_incomplete_backups_are_rejected(self):
        backup = Path(self.b.backup())
        for value in [{"schema": 1, "backend": "simapppro-v2"}, {"schema": 99, "backend": "simapppro-v1"}]:
            write(backup / "manifest.json", value)
            with self.assertRaises(shared.SetupError):
                self.b.validate_backup(backup)

    def test_debug_cleanup_preserves_presence_value_and_new_settings(self):
        for value in [None, False, True, "user-value"]:
            original = {"unrelated": 1}
            if value is not None:
                original["Debug"] = value
            write(self.b.global_config, original)
            self.b.enable_debug()
            cfg = self.b.load(self.b.global_config)
            self.assertIs(cfg["Debug"], True)
            cfg["new-setting"] = "keep"
            write(self.b.global_config, cfg)
            self.b.restore_debug()
            self.assertEqual(self.b.load(self.b.global_config), {**original, "new-setting": "keep"})
            self.assertFalse(self.b.session_file.exists())

    def test_only_owned_sets_are_removed(self):
        self.b.prepare_patch(20)
        keep = self.b.set_dir("My font")
        keep.mkdir()
        (keep / "keep.txt").touch()
        self.b.remove_patch_sets()
        self.assertFalse(self.b.set_dir(self.b.set_name).exists())
        self.assertTrue(keep.exists())
        self.assertTrue(self.b.set_dir("WWT_MCDU").exists())

    def test_invalid_set_names_cannot_escape_profile(self):
        for name in ["..", "../outside", "..\\outside", "C:\\outside", "a/b", ""]:
            with self.assertRaises(shared.SetupError):
                self.b.set_dir(name)

    def test_cdp_page_must_belong_to_selected_install(self):
        right = (Path(self.exe).parent / "resources" / "app.asar" / "view" / "index.html").as_uri()
        self.assertTrue(self.b.page_matches({"url": right}))
        self.assertFalse(self.b.page_matches({"url": "https://example.com/"}))
        self.assertFalse(self.b.page_matches({"url": right.replace("app.asar/", "app.asar-other/")}))

    def test_failed_upload_restores_debug_and_restarts(self):
        app = Mock()
        app.wait_ready.return_value = [self.api.font_name(f) for f in self.api.font_files()]
        app.call.side_effect = shared.SetupError("simulated upload failure")
        self.api.App = Mock(return_value=app)
        with self.assertRaisesRegex(shared.SetupError, "simulated"):
            self.b.mutate(self.ui, "install", 20)
        self.assertNotIn("Debug", self.b.load(self.b.global_config))
        self.assertFalse(self.b.session_file.exists())
        app.close.assert_called_once()
        self.assertEqual(self.b.start.call_args_list[-1].kwargs, {})
        self.assertEqual(len(list(self.b.backup_root.glob("*/manifest.json"))), 1)

    def test_check_is_read_only(self):
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        self.b.check()
        after = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.b.start.assert_not_called()
        self.b.stop.assert_not_called()

    def test_send_rasterizes_before_save_and_apply(self):
        app = Mock()
        app.call.return_value = [0, 0]
        self.b.send(app)
        body = app.call.call_args.args[0]
        self.assertLess(body.index("getFontConfigWithPixel"), body.index("saveFontConfigByKey"))
        self.assertLess(body.index("saveFontConfigByKey"), body.index("applyFont"))
        self.b.send(app, raster=False)
        self.assertNotIn("getFontConfigWithPixel", app.call.call_args.args[0])

    def test_restore_does_not_start_if_backup_is_invalid(self):
        with self.assertRaises(shared.SetupError):
            self.b.mutate(self.ui, "restore", src=self.folder / "missing")
        self.b.stop.assert_not_called()
        self.api.wait_for_mcdu.assert_not_called()

    def test_requires_admin_before_changing_or_closing_anything(self):
        self.api.is_admin.return_value = False
        with self.assertRaisesRegex(shared.SetupError, "administrator"):
            self.b.mutate(self.ui, "install", 20)
        self.b.stop.assert_not_called()
        self.assertFalse(self.b.backup_root.exists())

    def test_failed_factory_upload_keeps_patch_fonts_for_recovery(self):
        self.b.prepare_patch(20)
        app = Mock()
        app.wait_ready.return_value = []
        self.api.App = Mock(return_value=app)

        def reset_then_fail(_):
            cfg = self.b.load(self.b.config)
            cfg["fontConfig"]["fontSelected"] = "WWT_MCDU"
            self.b.save(self.b.config, cfg)
            raise shared.SetupError("USB upload failed")

        self.b.reset = reset_then_fail
        with self.assertRaisesRegex(shared.SetupError, "USB"):
            self.b.mutate(self.ui, "reset")
        self.assertTrue(self.b.set_dir(self.b.set_name).is_dir())
        self.assertFalse(self.b.session_file.exists())

    def test_socket_close_failure_still_restores_debug_and_restarts(self):
        app = Mock()
        app.wait_ready.return_value = [self.api.font_name(f) for f in self.api.font_files()]
        app.call.return_value = [0, 0]
        app.close.side_effect = OSError("socket closed")
        self.api.App = Mock(return_value=app)
        with self.assertRaisesRegex(OSError, "socket closed"):
            self.b.mutate(self.ui, "install", 20)
        self.assertFalse(self.b.session_file.exists())
        self.assertNotIn("Debug", self.b.load(self.b.global_config))
        self.assertEqual(self.b.start.call_args_list[-1].kwargs, {})


class DispatchTests(unittest.TestCase):
    def test_explicit_v1_check_dispatches_to_v1(self):
        with patch.object(shared.sys, "argv", ["setup_mcdu.py", "--simapppro", "1", "--check"]), \
             patch.object(shared, "ensure_packages"), patch.object(shared, "UI"), \
             patch("simapppro_v1.Backend") as backend:
            backend.return_value.run.return_value = 0
            self.assertEqual(shared.main(), 0)
            args = backend.return_value.run.call_args.args[1]
            self.assertEqual(args.simapppro, "1")
            self.assertTrue(args.check)

    def test_default_check_stays_on_v2(self):
        with patch.object(shared.sys, "argv", ["setup_mcdu.py", "--check"]), \
             patch.object(shared, "ensure_packages"), patch.object(shared, "UI"), \
             patch.object(shared.os.path, "exists", return_value=True), \
             patch.object(shared, "gamedisplay_dir", return_value="v2-profile"), \
             patch.object(shared, "cmd_check", return_value=True) as check, \
             patch("simapppro_v1.Backend") as backend:
            self.assertEqual(shared.main(), 0)
            check.assert_called_once()
            backend.assert_not_called()

    def test_interactive_selector_can_choose_v1(self):
        with patch.object(shared.sys, "argv", ["setup_mcdu.py"]), \
             patch.object(shared.sys.stdin, "isatty", return_value=True), \
             patch.object(shared, "ensure_packages"), patch.object(shared, "UI"), \
             patch.object(shared, "read_key", return_value="1"), \
             patch("simapppro_v1.discover_exe", return_value="installed"), \
             patch("simapppro_v1.Backend") as backend:
            backend.return_value.run.return_value = -1
            self.assertEqual(shared.main(), -1)
            self.assertEqual(backend.return_value.run.call_args.args[1].simapppro, "1")


class IPCContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed to execute the JS IPC adapter")
    def test_v1_result_normalization_and_channel_arguments(self):
        script = """
          const vm = require('vm'), assert = require('assert');
          const calls = []; let response = {};
          const context = {require: name => {
            assert.equal(name, 'electron');
            return {ipcRenderer: {sendSync: (channel, args) => {
              calls.push([channel, args]); return response;
            }}};
          }};
          const api = vm.runInNewContext(SOURCE, context).k;
          assert.equal(api.CDU_changeDeviceId({deviceId:'MCDU'}).status, 0);
          assert.equal(calls[0][0], 'CDU-changeDeviceId');
          assert.equal(calls[0][1].deviceId, 'MCDU');
          response={data:[{fontName:'test'}]};
          assert.equal(api.CDU_getPcFontArray().data[0].fontName, 'test');
          for (const bad of [undefined,null,[],false,0,'bad',{errMsg:'failed'}]) {
            response=bad; assert.throws(()=>api.CDU_applyFont());
          }
          console.log('IPC contract passed');
        """.replace("SOURCE", json.dumps(IPC_API))
        result = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
