#!/usr/bin/env python3
"""Idempotent runtime configuration for Fusion on XFCE/X11."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

DEFAULT_X11_KEY = r'HKCU\Software\Wine\X11 Driver'
FUSION_X11_KEY = r'HKCU\Software\Wine\AppDefaults\fusion360.exe\X11 Driver'
WEBVIEW_APP_KEY = r'HKCU\Software\Wine\AppDefaults\msedgewebview2.exe'


def reg(*args):
    subprocess.run([os.environ.get('WINE', 'wine'), 'reg', *args], check=True,
                   timeout=45, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def yn(name, default):
    value = os.environ.get(name, default).upper()
    if value not in {'Y', 'N'}:
        raise ValueError(f'{name} must be Y or N')
    return value


def set_reg_sz(key, name, value):
    reg('add', key, '/f')
    reg('add', key, '/v', name, '/t', 'REG_SZ', '/d', value, '/f')


def configure_wine():
    values = {
        'Managed': yn('FUSION_WINDOW_MANAGED', 'Y'),
        # Legacy 3.1.x option. It is ignored by the custom Wine driver while
        # FusionWindowPolicy=Y, but is retained for painless upgrades/rollback.
        'UnmanageOwnedWindows': yn('FUSION_UNMANAGE_OWNED_WINDOWS', 'N'),
        'FusionWindowPolicy': yn('FUSION_WINDOW_POLICY', 'Y'),
        'Decorated': yn('FUSION_WINDOW_DECORATED', 'Y'),
        'UseTakeFocus': yn('FUSION_USE_TAKE_FOCUS', 'N'),
    }
    # Apply the classifier prefix-wide so helper-process file choosers use it too.
    set_reg_sz(DEFAULT_X11_KEY, 'FusionWindowPolicy', values['FusionWindowPolicy'])
    set_reg_sz(DEFAULT_X11_KEY, 'UnmanageOwnedWindows', 'N')

    reg('add', FUSION_X11_KEY, '/f')
    for name, value in values.items():
        reg('add', FUSION_X11_KEY, '/v', name, '/t', 'REG_SZ', '/d', value, '/f')

    # WebView2 compatibility is independent from X11 stacking. Scope the Windows
    # version override to the helper executable only; Fusion itself stays win10.
    set_reg_sz(WEBVIEW_APP_KEY, 'Version', os.environ.get('FUSION_WEBVIEW2_WINVER', 'win8'))

    print('Fusion X11: ' + ', '.join(f'{k}={v}' for k, v in values.items()), flush=True)
    print('WebView2 Version=' + os.environ.get('FUSION_WEBVIEW2_WINVER', 'win8'), flush=True)


class Display:
    def __init__(self):
        self.x = C.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
        for name, restype, argtypes in (
            ('XOpenDisplay', C.c_void_p, [C.c_char_p]),
            ('XDefaultScreen', C.c_int, [C.c_void_p]),
            ('XInternAtom', C.c_ulong, [C.c_void_p, C.c_char_p, C.c_int]),
            ('XGetSelectionOwner', C.c_ulong, [C.c_void_p, C.c_ulong]),
            ('XCloseDisplay', C.c_int, [C.c_void_p]),
        ):
            fn = getattr(self.x, name)
            fn.restype, fn.argtypes = restype, argtypes
        self.d = self.x.XOpenDisplay(None)
        if not self.d:
            raise RuntimeError('Cannot open desktop DISPLAY')
        screen = self.x.XDefaultScreen(self.d)
        # ICCCM: the active window manager owns WM_Sn; the compositor owns
        # _NET_WM_CM_Sn.  These are separate selections and must not be
        # treated as interchangeable during XFCE startup.
        self.wm_atom = self.x.XInternAtom(self.d, f'WM_S{screen}'.encode(), 0)
        self.atom = self.x.XInternAtom(self.d, f'_NET_WM_CM_S{screen}'.encode(), 0)

    def window_manager_owner(self):
        return self.x.XGetSelectionOwner(self.d, self.wm_atom)

    def owner(self):
        return self.x.XGetSelectionOwner(self.d, self.atom)

    def close(self):
        self.x.XCloseDisplay(self.d)


def wait_for_window_manager(display, timeout=60):
    """Let XFCE start xfwm4; Fusion must never start/replace the WM itself."""
    deadline = time.monotonic() + timeout
    while not display.window_manager_owner():
        if time.monotonic() >= deadline:
            raise RuntimeError(
                'No active X11 window manager after 60 seconds; '
                'check the XFCE session before launching Fusion.'
            )
        time.sleep(0.25)


def ensure_compositor():
    display = Display()
    try:
        # A reachable X server is not proof that XFCE has finished starting.
        # The former fallback launched xfwm4 --replace --vblank=off when the
        # compositor selection was temporarily unowned, racing XFCE startup
        # and sometimes leaving the desktop without a working window manager.
        wait_for_window_manager(display)
        if display.owner():
            return
        for args in (
            ['xfconf-query', '-c', 'xfwm4', '-p', '/general/use_compositing', '-s', 'true'],
            ['xfconf-query', '-c', 'xfwm4', '-p', '/general/use_compositing', '-n', '-t', 'bool', '-s', 'true'],
        ):
            if subprocess.run(args, timeout=5, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                break
        for _ in range(30):
            if display.owner():
                return
            time.sleep(0.2)
        # Do not forcibly replace XFCE's window manager: compositor readiness
        # is distinct from WM readiness. Fusion can still run without effects.
        print('Fusion X11: XFCE compositor unavailable; proceeding without '
              'restarting the window manager.', flush=True)
    finally:
        display.close()


def patch_options(path: Path, api: str):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(path, parser=parser) if path.exists() else ET.ElementTree(ET.Element('OptionGroups'))
    root = tree.getroot()
    if root.tag != 'OptionGroups':
        raise ValueError(f'Unexpected XML root in {path}')
    nodes = root.findall('.//graphicsApiOptionId')
    if nodes and all(node.get('Value') == api for node in nodes):
        return False
    if not nodes:
        group = root.find('CompatibilityGroup')
        if group is None:
            group = ET.SubElement(root, 'CompatibilityGroup', SchemaVersion='2')
        nodes = [ET.SubElement(group, 'graphicsApiOptionId',
                               UserName='Qt Rendering Hardware Interface API')]
    for node in nodes:
        node.set('Value', api)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.fusion-options-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            tree.write(stream, encoding='utf-8', xml_declaration=True)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return True


def configure_graphics():
    api = os.environ.get('FUSION_UI_API', 'OpenGL')
    if api == 'keep':
        return
    if api != 'OpenGL':
        raise ValueError('FUSION_UI_API must be OpenGL or keep')
    prefix = Path(os.environ['WINEPREFIX'])
    for area in ('Local', 'Roaming'):
        path = prefix / f'drive_c/users/abc/AppData/{area}/Autodesk/Neutron Platform/Options/NMachineSpecificOptions.xml'
        patch_options(path, api)


def main():
    ensure_compositor()
    configure_wine()
    configure_graphics()


if __name__ == '__main__':
    main()
