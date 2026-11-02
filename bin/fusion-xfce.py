#!/usr/bin/env python3
"""Configure XFCE compositing before its X11 session is started.

The desktop uses Mesa GLX (the image default), while Fusion selects its
own renderer.  A previous 3.4.2 release disabled compositing for NVIDIA;
restore it when an NVIDIA device is available so Fusion popup windows work.
"""
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET


def compositor_policy(env, devices):
    mode = env.get('FUSION_XFCE_COMPOSITOR', 'auto').lower()
    if mode not in {'auto', 'on', 'off'}:
        raise ValueError('FUSION_XFCE_COMPOSITOR must be auto, on, or off')
    if mode == 'auto':
        # Upgrade recovery: 3.4.2 persisted use_compositing=false on NVIDIA.
        # For other systems, respect the existing desktop preference.
        nvidia_present = any(re.fullmatch(r'nvidia[0-9]+', p.name) and p.is_char_device()
                             for p in devices)
        return True if nvidia_present else None
    return mode == 'on'


def set_compositor_config(path, enabled):
    path = Path(path)
    if enabled is None:
        return False
    if path.exists():
        tree = ET.parse(path)
        root = tree.getroot()
        if root.tag != 'channel' or root.get('name') != 'xfwm4':
            raise ValueError(f'Unexpected XFCE config document: {path}')
    else:
        root = ET.Element('channel', name='xfwm4', version='1.0')
        tree = ET.ElementTree(root)
    general = root.find("./property[@name='general']")
    if general is None:
        general = ET.SubElement(root, 'property', name='general', type='empty')
    item = general.find("./property[@name='use_compositing']")
    value = 'true' if enabled else 'false'
    if item is not None and item.get('type') == 'bool' and item.get('value') == value:
        return False
    if item is None:
        item = ET.SubElement(general, 'property', name='use_compositing')
    item.set('type', 'bool')
    item.set('value', value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + '.fusion-original')
        if not backup.exists():
            shutil.copy2(path, backup)
    fd, temp = tempfile.mkstemp(prefix='.xfwm4-fusion-', suffix='.xml', dir=path.parent)
    try:
        ET.indent(tree, space='  ')
        with os.fdopen(fd, 'wb') as output:
            tree.write(output, encoding='utf-8', xml_declaration=True)
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return True


def main():
    path = Path(os.environ.get('HOME', '/config')) / '.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml'
    policy = compositor_policy(os.environ, Path('/dev').glob('nvidia*'))
    changed = set_compositor_config(path, policy)
    print(f'Fusion XFCE compositor: {"unchanged" if policy is None else "on" if policy else "off"}'
          f' (changed={changed}; applied before XFCE startup)', flush=True)


if __name__ == '__main__':
    main()
