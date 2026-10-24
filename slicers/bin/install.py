#!/usr/bin/env python3
"""Install pinned upstream AppImages without FUSE; verify downloads and ELF deps."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def download(item, cache):
    target = cache / (item['sha256'] + '.AppImage')
    if target.exists() and digest(target) == item['sha256']:
        return target
    target.unlink(missing_ok=True)
    partial = target.with_suffix('.part')
    for attempt in range(3):
        # A lost connection can resume on the next attempt/build.
        result = subprocess.run([
            'curl', '-fL', '--retry', '3', '--retry-all-errors',
            '--connect-timeout', '20', '--speed-limit', '1024', '--speed-time', '60',
            '--max-time', '1800', '--continue-at', '-',
            '--output', str(partial), item['url']])
        if result.returncode == 0:
            if digest(partial) == item['sha256']:
                partial.replace(target)
                return target
            partial.unlink(missing_ok=True)
        elif result.returncode in (33, 36):
            partial.unlink(missing_ok=True)  # Server cannot resume this object.
    raise RuntimeError(f"Could not download and verify {item['name']}; rerun build to resume")


def install(item, image, destination):
    image.chmod(0o755)
    with tempfile.TemporaryDirectory(prefix='slicer-extract-') as tmp:
        log = Path(tmp) / 'extract.log'
        with log.open('w') as out:
            subprocess.run([str(image), '--appimage-extract'], cwd=tmp, stdout=out, check=True)
        root = Path(tmp) / 'squashfs-root'
        if not (root / 'AppRun').exists() or not (root / 'bin' / item['binary']).exists():
            raise RuntimeError(f"Unexpected AppImage layout: {item['name']}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(root), destination)
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = ':'.join(str(destination / s) for s in ('lib/orca-runtime', 'bin', 'lib'))
    result = subprocess.run(['ldd', str(destination / 'bin' / item['binary'])],
                            env=env, capture_output=True, text=True, check=True)
    if 'not found' in result.stdout:
        raise RuntimeError('Missing slicer dependencies:\n' + result.stdout)
    print(f"Installed {item['name']} {item['version']}; ELF dependencies resolved", flush=True)


if __name__ == '__main__':
    releases = json.loads(Path(__file__).with_name('releases.json').read_text())
    cache = Path('/var/cache/fusion-slicers')
    cache.mkdir(parents=True, exist_ok=True)
    for item in releases:
        install(item, download(item, cache), Path('/opt') / item['name'])
    Path('/opt/fusion-lab/slicers/installed.json').write_text(json.dumps(releases, indent=2) + '\n')
