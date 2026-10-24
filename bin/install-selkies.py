#!/usr/bin/env python3
"""Inject invisible fullscreen keyboard-lock support into installed Selkies dashboards."""
from pathlib import Path
import shutil

JS_SOURCE = Path('/opt/fusion-lab/web/fusion-keyboard.js')
MARKER = '<script defer src="./fusion-keyboard.js?v=3"></script>'


def find_indexes(root=Path('/usr/share/selkies')):
    candidates = [
        root / 'www/index.html',
        root / 'web/index.html',
        root / 'selkies-dashboard/index.html',
        root / 'selkies-dashboard-wish/index.html',
        root / 'selkies-dashboard-zinc/index.html',
    ]
    found = [p for p in candidates if p.is_file()]
    if root.is_dir():
        for p in root.glob('*/index.html'):
            if p.is_file() and p not in found:
                found.append(p)
    return found


def patch(index: Path, js_source=JS_SOURCE):
    html = index.read_text(encoding='utf-8')
    if MARKER not in html:
        lower = html.lower()
        if '</head>' in lower:
            pos = lower.index('</head>')
            html = html[:pos] + MARKER + '\n' + html[pos:]
        elif '</body>' in lower:
            pos = lower.index('</body>')
            html = html[:pos] + MARKER + '\n' + html[pos:]
        else:
            html = html.rstrip() + '\n' + MARKER + '\n'
        index.write_text(html, encoding='utf-8')
    shutil.copyfile(js_source, index.parent / 'fusion-keyboard.js')


def main():
    if not JS_SOURCE.is_file():
        raise SystemExit(f'Keyboard integration JS missing: {JS_SOURCE}')
    indexes = find_indexes()
    if not indexes:
        raise SystemExit('Selkies index.html missing')
    for index in indexes:
        patch(index)
        print(f'Selkies keyboard integration: {index}')


if __name__ == '__main__':
    main()
