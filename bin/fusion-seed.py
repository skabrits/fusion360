#!/usr/bin/env python3
"""Seed only an absent Fusion directory. Never overwrite a user's prefix."""
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import shutil


def has_install(root):
    prefix = root / 'wineprefixes/default'
    return ((prefix / 'system.reg').is_file()
            and any((prefix / 'drive_c').rglob('Fusion360.exe'))
            and any((prefix / 'drive_c').rglob('AdskIdentityManager.exe')))


def seed(config, factory):
    target = config / '.autodesk_fusion'
    if target.exists() or target.is_symlink():
        if has_install(target):
            print('Fusion: preserving existing installation and login.')
            return
        raise RuntimeError('Existing Fusion directory is incomplete; preserved unchanged. '
                           'Move it aside after backup before using a factory seed.')
    archive = factory / 'prefix.tar.gz'
    checksum = factory / 'prefix.tar.gz.sha256'
    if not archive.is_file() or not checksum.is_file():
        raise RuntimeError('No installed prefix and no factory seed. Build target ready, not runtime.')
    expected = checksum.read_text().split()[0]
    with archive.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError('Factory prefix checksum mismatch; refusing to extract.')
    # Seed is produced by this image build, never downloaded at runtime. GNU tar rejects
    # traversal member names; preserve Wine's legitimate drive-letter symlinks.
    staging = pathlib.Path(tempfile.mkdtemp(prefix='.fusion-seed-', dir=config))
    try:
        subprocess.run(['tar', '--extract', '--gzip', '--file', str(archive),
                        '--directory', str(staging), '--no-same-owner'], check=True)
        candidate = staging / '.autodesk_fusion'
        if not has_install(candidate):
            raise RuntimeError('Factory seed lacks Fusion, Identity Manager, or registry.')
        if target.exists() or target.is_symlink():
            raise RuntimeError('Fusion directory appeared during extraction; refusing replacement.')
        candidate.rename(target)
        print('Fusion: factory installation ready; no runtime download required.')
    finally:
        shutil.rmtree(staging)


if __name__ == '__main__':
    try:
        seed(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
    except Exception as exc:
        sys.exit(f'Fusion initialization failed: {exc}')
