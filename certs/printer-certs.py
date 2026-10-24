#!/usr/bin/env python3
"""Capture stock printer trust stores at build; merge optional CA at startup."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PEM = re.compile(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', re.S)
STATE = Path('/opt/fusion-lab/printer-certs')


def certificates(data):
    if b'PRIVATE KEY' in data:
        raise ValueError('Supply public CA certificates only, not a private key')
    blocks = PEM.findall(data)
    if not blocks or PEM.sub(b'', data).strip():
        raise ValueError('Expected PEM certificates (BEGIN CERTIFICATE), with no extra text')
    normalized = []
    for block in blocks:
        result = subprocess.run(['openssl', 'x509', '-inform', 'PEM', '-outform', 'PEM'],
                                input=block, capture_output=True)
        if result.returncode:
            raise ValueError('Invalid X.509 certificate')
        if result.stdout not in normalized:
            normalized.append(result.stdout)
    return normalized


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def capture(state=STATE, roots=None):
    roots = roots or [Path('/opt/bambustudio'), Path('/opt/orcaslicer')]
    state.mkdir(parents=True, exist_ok=True)
    manifest = []
    for root in roots:
        targets = sorted(set(p.resolve() for p in root.rglob('printer.cer')))
        if not targets:
            raise ValueError(f'No printer.cer found under {root}; unexpected slicer layout')
        for path in targets:
            data = path.read_bytes()
            certificates(data)
            backup = state / f'{len(manifest)}.pem'
            atomic_write(backup, data)
            manifest.append({'target': str(path), 'original': str(backup)})
    atomic_write(state / 'manifest.json', json.dumps(manifest).encode())


def apply(source, state=STATE, bundle=Path('/run/slicer-certs/ca-bundle.pem'),
          system_ca=Path('/etc/ssl/certs/ca-certificates.crt')):
    # Validate every input before changing any target.
    extra = certificates(Path(source).read_bytes()) if source else []
    updates = []
    for item in json.loads((state / 'manifest.json').read_text()):
        original = Path(item['original']).read_bytes()
        stock = certificates(original)
        merged = stock + [c for c in extra if c not in stock]
        updates.append((Path(item['target']), b''.join(merged) if source else original))
    bundle_data = system_ca.read_bytes().rstrip() + b'\n' + b''.join(extra) if source else None
    for path, data in updates:
        atomic_write(path, data)
    if source:
        atomic_write(bundle, bundle_data)
    else:
        bundle.unlink(missing_ok=True)
    print(f'Printer certificates: {len(extra)} custom certificate(s), {len(updates)} slicer store(s) updated')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--capture']:
            capture()
        elif not sys.argv[1:]:
            apply(os.environ.get('BAMBUDDY_CERT_FILE', '').strip())
        else:
            raise ValueError('Usage: printer-certs.py [--capture]')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(f'Printer certificate setup failed: {error}')
