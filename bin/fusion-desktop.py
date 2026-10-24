#!/usr/bin/env python3
"""Install an XFCE desktop launcher and, when possible, extract Fusion's real icon."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CONFIG = Path('/config')
APP = Path('/usr/share/applications/autodesk-fusion.desktop')
DESKTOP = CONFIG / 'Desktop' / 'autodesk-fusion.desktop'
LOCAL_APP = CONFIG / '.local/share/applications/autodesk-fusion.desktop'
ICON_DIR = CONFIG / '.local/share/icons/hicolor/256x256/apps'
ICON = ICON_DIR / 'autodesk-fusion.png'


def install_file(src: Path, dst: Path, mode: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    os.chmod(dst, mode)


def find_fusion_exe() -> Path | None:
    prefix = CONFIG / '.autodesk_fusion/wineprefixes/default/drive_c'
    if not prefix.is_dir():
        return None
    matches = list(prefix.rglob('Fusion360.exe'))
    return matches[0] if matches else None


def extract_icon(exe: Path) -> None:
    if ICON.exists() or not shutil.which('wrestool') or not shutil.which('icotool'):
        return
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fusion-icon-') as d:
        tmp = Path(d)
        ico_dir = tmp / 'ico'
        png_dir = tmp / 'png'
        ico_dir.mkdir(); png_dir.mkdir()
        subprocess.run(['wrestool', '-x', '-t14', '-o', str(ico_dir), str(exe)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        candidates = sorted(ico_dir.glob('*.ico'))
        for ico in candidates:
            subprocess.run(['icotool', '-x', '-o', str(png_dir), str(ico)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        pngs = list(png_dir.glob('*.png'))
        if not pngs:
            return
        # The largest PNG resource is normally the highest-resolution application icon.
        chosen = max(pngs, key=lambda p: p.stat().st_size)
        shutil.copyfile(chosen, ICON)
        os.chmod(ICON, 0o644)


def main() -> None:
    install_file(APP, LOCAL_APP, 0o644)
    install_file(APP, DESKTOP, 0o755)
    exe = find_fusion_exe()
    if exe:
        # The system fallback SVG already makes the launcher usable.  Extracting
        # Autodesk's embedded icon is cosmetic and must never abort container init.
        try:
            extract_icon(exe)
        except OSError as exc:
            print(f"Fusion launcher: embedded icon extraction skipped: {exc}", flush=True)


if __name__ == '__main__':
    main()
