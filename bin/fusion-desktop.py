#!/usr/bin/env python3
"""Install an XFCE desktop launcher and, when possible, extract Fusion's real icon."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

CONFIG = Path('/config')
APP = Path('/usr/share/applications/autodesk-fusion.desktop')
DESKTOP = CONFIG / 'Desktop' / 'autodesk-fusion.desktop'
LOCAL_APP = CONFIG / '.local/share/applications/autodesk-fusion.desktop'
ICON_DIR = CONFIG / '.local/share/icons/hicolor/256x256/apps'
ICON = ICON_DIR / 'autodesk-fusion.png'
STAMP = ICON_DIR / '.autodesk-fusion-source.sha256'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def production_dirs(config: Path):
    drive = config / '.autodesk_fusion/wineprefixes/default/drive_c'
    bases = [
        drive / 'Program Files/Autodesk/webdeploy/production',
        drive / 'Program Files (x86)/Autodesk/webdeploy/production',
        drive / 'users/abc/AppData/Local/Autodesk/webdeploy/production',
    ]
    for base in bases:
        if base.is_dir():
            yield from (p for p in base.iterdir() if p.is_dir())


def icon_sources(config: Path):
    """Yield candidates for installed Fusion, trying other ICOs on failure.

    Some Autodesk versions put a PNG-compressed ICO at the production root;
    others also ship a usable copy under an internal add-in's resources.
    Do not stop at a malformed or unsupported top-level file.
    """
    dirs = sorted(production_dirs(config), key=lambda p: (
        (p / 'Fusion360.exe').is_file(),
        (p / 'Fusion360.exe').stat().st_mtime_ns if (p / 'Fusion360.exe').is_file()
        else p.stat().st_mtime_ns,
    ), reverse=True)
    found = set()
    for d in dirs:
        candidates = [d / 'Fusion360.ico']
        candidates.extend(sorted(d.glob('API/InternalAddins/*/resources/Fusion360.ico')))
        for candidate in candidates:
            if candidate.is_file() and candidate not in found:
                found.add(candidate)
                yield candidate, 'ico'
    # PE resources remain the last resort.
    for exe_name in ('FusionLauncher.exe', 'Fusion360.exe'):
        for d in dirs:
            candidate = d / exe_name
            if candidate.is_file() and candidate not in found:
                found.add(candidate)
                yield candidate, 'pe'


def find_icon_source(config: Path):
    """Return the preferred source for compatibility with diagnostics/tests."""
    return next(icon_sources(config), (None, None))


def ico_embedded_png(source: Path):
    """Read PNG-compressed ICO frames directly, without icotool/Pillow.

    In PNG-compressed Windows ICOs, each ICONDIRENTRY points directly to
    a complete PNG stream. icotool on some builds cannot decode this form.
    """
    data = source.read_bytes()
    if len(data) < 6 or data[:4] != b'\x00\x00\x01\x00':
        return None
    count = struct.unpack_from('<H', data, 4)[0]
    if not 0 < count <= 512 or len(data) < 6 + count * 16:
        return None
    frames = []
    for i in range(count):
        # ICONDIRENTRY layout: width, height, colors, reserved,
        # planes, bpp, dwBytesInRes, dwImageOffset.
        size, offset = struct.unpack_from('<II', data, 6 + 16 * i + 8)
        if not size or offset < 6 + count * 16 or offset + size > len(data):
            continue
        payload = data[offset:offset + size]
        if (len(payload) < 45 or payload[:8] != PNG_MAGIC
                or payload[12:16] != b'IHDR'
                or not payload.endswith(b'IEND\xaeB`\x82')):
            continue
        width, height = struct.unpack_from('>II', payload, 16)
        if 0 < width <= 8192 and 0 < height <= 8192:
            frames.append(((width, height), payload))
    if not frames:
        return None
    return max(frames, key=lambda frame: (
        frame[0] == (256, 256),
        min(frame[0]) <= 512,
        min(frame[0]),
        len(frame[1]),
    ))[1]


def write_icon_png(destination: Path, data: bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = destination.with_name('.autodesk-fusion-pending.png')
    try:
        tmp_dest.write_bytes(data)
        if not png_size(tmp_dest):
            raise RuntimeError('Extracted image is not a PNG')
        os.chmod(tmp_dest, 0o644)
        os.replace(tmp_dest, destination)
    finally:
        tmp_dest.unlink(missing_ok=True)


def png_size(path: Path):
    with path.open('rb') as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != PNG_MAGIC or header[12:16] != b'IHDR':
        return None
    width, height = struct.unpack('>II', header[16:24])
    if not (0 < width <= 8192 and 0 < height <= 8192):
        return None
    return width, height


def convert_icon(source: Path, kind: str, destination: Path):
    if kind == 'ico':
        embedded = ico_embedded_png(source)
        if embedded is not None:
            write_icon_png(destination, embedded)
            return

    if not shutil.which('icotool'):
        raise RuntimeError('No embedded PNG frames and icotool unavailable')
    with tempfile.TemporaryDirectory(prefix='fusion-icon-') as work:
        tmp = Path(work)
        png_dir = tmp / 'png'
        png_dir.mkdir()
        if kind == 'ico':
            ico_files = [source]
        else:
            if not shutil.which('wrestool'):
                raise RuntimeError('wrestool unavailable (install icoutils)')
            ico_dir = tmp / 'ico'
            ico_dir.mkdir()
            subprocess.run(['wrestool', '-x', '-t14', '-o', str(ico_dir), str(source)],
                           check=False, capture_output=True, timeout=45)
            ico_files = list(ico_dir.glob('*.ico'))
        for ico in ico_files:
            embedded = ico_embedded_png(ico)
            if embedded is not None:
                write_icon_png(destination, embedded)
                return
            subprocess.run(['icotool', '-x', '-o', str(png_dir), str(ico)],
                           check=False, capture_output=True, timeout=45)
        candidates = [(p, png_size(p)) for p in png_dir.glob('*.png')]
        candidates = [(p, size) for p, size in candidates if size]
        if not candidates:
            raise RuntimeError(f'No convertible PNG frames in {source}')
        chosen, _ = max(candidates, key=lambda pair: (
            pair[1] == (256, 256),
            min(pair[1]) <= 512,
            min(pair[1]),
            pair[0].stat().st_size,
        ))
        write_icon_png(destination, chosen.read_bytes())


def ensure_icon(config: Path, icon: Path, stamp: Path):
    attempted = False
    for source, kind in icon_sources(config):
        attempted = True
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if (icon.is_file() and stamp.is_file()
                    and stamp.read_text().strip() == digest):
                return icon
            convert_icon(source, kind, icon)
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(digest + '\n')
            os.chmod(stamp, 0o644)
            print(f'Fusion launcher: icon extracted from {source}', flush=True)
            return icon
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f'Fusion launcher: icon extraction failed ({source}): {exc}', flush=True)
    if not attempted:
        print('Fusion launcher: no Fusion icon source found; using theme fallback.', flush=True)
    return icon if icon.is_file() else None


def launcher_text(template: str, icon: Path | None):
    icon_value = str(icon) if icon else 'autodesk-fusion'
    # An absolute icon path avoids icon-theme lookup ordering and stale caches.
    return '\n'.join('Icon=' + icon_value if line.startswith('Icon=') else line
                     for line in template.split('\n'))


def install_launcher(path: Path, content: str, mode: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
    os.chmod(path, mode)


def main():
    icon = ensure_icon(CONFIG, ICON, STAMP)
    content = launcher_text(APP.read_text(), icon)
    install_launcher(LOCAL_APP, content, 0o644)
    install_launcher(DESKTOP, content, 0o755)


if __name__ == '__main__':
    main()
