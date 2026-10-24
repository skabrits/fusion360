import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RuntimeConfigTests(unittest.TestCase):
    def test_default_hybrid_window_policy(self):
        mod = load(ROOT/'bin/fusion-runtime.py', 'fusion_runtime')
        calls = []
        env = dict(mod.os.environ)
        for key in ('FUSION_WINDOW_MANAGED', 'FUSION_UNMANAGE_OWNED_WINDOWS',
                    'FUSION_WINDOW_POLICY', 'FUSION_WINDOW_DECORATED', 'FUSION_USE_TAKE_FOCUS'):
            env.pop(key, None)
        with patch.object(mod, 'reg', side_effect=lambda *a: calls.append(a)), \
             patch.dict(mod.os.environ, env, clear=True):
            mod.configure_wine()
        joined = [' '.join(c) for c in calls]
        self.assertTrue(any('/v Managed' in c and '/d Y' in c for c in joined))
        self.assertTrue(any('/v UnmanageOwnedWindows' in c and '/d N' in c for c in joined))
        self.assertTrue(any('/v FusionWindowPolicy' in c and '/d Y' in c for c in joined))
        self.assertTrue(any('Software\\Wine\\X11 Driver' in c and '/v FusionWindowPolicy' in c and '/d Y' in c for c in joined))
        self.assertTrue(any('msedgewebview2.exe' in c and '/v Version' in c and '/d win8' in c for c in joined))
        self.assertTrue(any('/v Decorated' in c and '/d Y' in c for c in joined))
        self.assertTrue(any('/v UseTakeFocus' in c and '/d N' in c for c in joined))

    def test_owned_window_patch_can_be_disabled(self):
        mod = load(ROOT/'bin/fusion-runtime.py', 'fusion_runtime_optout')
        calls = []
        with patch.object(mod, 'reg', side_effect=lambda *a: calls.append(a)), \
             patch.dict(mod.os.environ, {'FUSION_UNMANAGE_OWNED_WINDOWS': 'N'}, clear=False):
            mod.configure_wine()
        self.assertTrue(any('/v UnmanageOwnedWindows' in ' '.join(c) and '/d N' in ' '.join(c)
                            for c in calls))

    def test_wine_source_transform_is_narrow_and_opt_in(self):
        text = (ROOT/'patches/apply-wine-fusion.py').read_text()
        self.assertIn('UnmanageOwnedWindows', text)
        self.assertIn('FusionWindowPolicy', text)
        self.assertIn('Primary/unowned application frames must always stay managed.', text)
        self.assertNotIn('(style & WS_DLGFRAME)) return FALSE', text)
        self.assertIn('BOOL fusion_window_policy = FALSE;', text)
        self.assertIn('expected exactly one', text)

    def test_wine_source_transform_applies_to_post_staging_shape(self):
        mod = load(ROOT/'patches/apply-wine-fusion.py', 'apply_wine_fusion')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            drv = root/'dlls/winex11.drv'
            drv.mkdir(parents=True)
            (drv/'x11drv.h').write_text('before\nextern BOOL managed_mode;\nafter\n')
            (drv/'x11drv_main.c').write_text(
                'BOOL managed_mode = TRUE;\n'
                'unrelated staging insertion\n'
                '    if (!get_config_key( hkey, appkey, "Managed", buffer, sizeof(buffer) ))\n'
                '        managed_mode = IS_OPTION_TRUE( buffer[0] );\n'
                '    if (!get_config_key( hkey, appkey, "SomeStagingOption", buffer, sizeof(buffer) ))\n'
                '        staging_option = IS_OPTION_TRUE( buffer[0] );\n'
            )
            (drv/'window.c').write_text(
                'prefix\n'
                '    /* child windows are not managed */\n'
                '    style = NtUserGetWindowLongW( hwnd, GWL_STYLE );\n'
                '    if ((style & (WS_CHILD|WS_POPUP)) == WS_CHILD) return FALSE;\n'
                'suffix\n'
            )
            mod.apply(root)
            main = (drv/'x11drv_main.c').read_text()
            window = (drv/'window.c').read_text()
            self.assertIn('BOOL unmanage_owned_windows = FALSE;', main)
            self.assertIn('BOOL fusion_window_policy = FALSE;', main)
            self.assertIn('"FusionWindowPolicy"', main)
            self.assertIn('SomeStagingOption', main)
            self.assertIn('WS_EX_TOOLWINDOW', window)
            self.assertIn('WS_EX_DLGMODALFRAME', window)
            self.assertIn('if (!owner && (resizable || app_window || captioned)) return TRUE;', window)
            self.assertNotIn('(style & WS_DLGFRAME)) return FALSE', window)

    def test_browser_flags_are_split_by_engine(self):
        mod = load(ROOT/'bin/flags.py', 'fusion_flags_split')
        with patch.dict(mod.os.environ, {}, clear=True):
            self.assertEqual(mod.policy('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'), (False, True))
            self.assertEqual(mod.policy('QTWEBENGINE_CHROMIUM_FLAGS'), (False, False))
        with patch.dict(mod.os.environ, {'FUSION_WEBVIEW2_DISABLE_GPU':'1'}, clear=True):
            self.assertEqual(mod.policy('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'), (True, True))

    def test_aux_policy_can_be_disabled(self):
        mod = load(ROOT/'bin/fusion-runtime.py', 'fusion_runtime_aux_optout')
        calls = []
        with patch.object(mod, 'reg', side_effect=lambda *a: calls.append(a)), \
             patch.dict(mod.os.environ, {'FUSION_WINDOW_POLICY': 'N'}, clear=False):
            mod.configure_wine()
        self.assertTrue(any('/v FusionWindowPolicy' in ' '.join(c) and '/d N' in ' '.join(c)
                            for c in calls))

    def test_desktop_launcher_is_installed(self):
        desktop = (ROOT/'root/usr/share/applications/autodesk-fusion.desktop').read_text()
        init = (ROOT/'root/custom-cont-init.d/50-fusion').read_text()
        helper = (ROOT/'bin/fusion-desktop.py').read_text()
        self.assertIn('Exec=/opt/fusion-lab/bin/fusion-run', desktop)
        self.assertIn('Icon=autodesk-fusion', desktop)
        self.assertIn('Actions=Restart;', desktop)
        self.assertIn('Exec=/opt/fusion-lab/bin/fusion-restart', desktop)
        self.assertIn('/config/Desktop', init)
        self.assertIn('/config/.local/share/icons/hicolor/256x256/apps', init)
        self.assertIn('install -d -o abc -g abc', init)
        self.assertIn('fusion-desktop.py', init)
        self.assertIn('wrestool', helper)
        self.assertIn('icotool', helper)
        self.assertIn('embedded icon extraction skipped', helper)

    def test_launcher_releases_lock_before_wine_exec(self):
        launcher = (ROOT/'bin/fusion-run').read_text()
        restart = (ROOT/'bin/fusion-restart').read_text()
        unlock = launcher.index('flock -u 8')
        closefd = launcher.index('exec 8>&-')
        wineexec = launcher.index('exec "$WINE" "$exe"')
        self.assertLess(unlock, closefd)
        self.assertLess(closefd, wineexec)
        self.assertIn('"$WINESERVER" -k', restart)
        self.assertIn('"$WINESERVER" -w', restart)


    def test_selkies_layout_fallbacks(self):
        mod = load(ROOT/'bin/install-selkies.py', 'install_selkies')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root/'web/index.html'; a.parent.mkdir(); a.write_text('<html><head></head><body></body></html>')
            b = root/'future/index.html'; b.parent.mkdir(); b.write_text('<html><body></body></html>')
            found = mod.find_indexes(root)
            self.assertIn(a, found)
            self.assertIn(b, found)

    def test_selkies_patch_has_no_capture_button(self):
        mod = load(ROOT/'bin/install-selkies.py', 'install_selkies_patch')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            idx = root/'index.html'; idx.write_text('<html><head></head><body></body></html>')
            js = root/'source.js'; js.write_text('// invisible')
            mod.patch(idx, js)
            text = idx.read_text()
            self.assertIn('fusion-keyboard.js?v=3', text)
            self.assertNotIn('Capture keyboard', text)
            self.assertEqual((root/'fusion-keyboard.js').read_text(), '// invisible')


if __name__ == '__main__':
    unittest.main()
