#!/usr/bin/env python3
import os, shlex, sys


def bool_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'y', 'yes', 'true', 'on'}


def flags(value, disable_gpu=False, no_sandbox=False):
    args = shlex.split(value)
    # Normalize only switches that this launcher owns. Proxy switches are handled later.
    args = [a for a in args if a.split('=', 1)[0] not in {'--disable-gpu', '--no-sandbox'}]
    if disable_gpu:
        args.append('--disable-gpu')
    if no_sandbox:
        args.append('--no-sandbox')
    return shlex.join(args)


def policy(varname):
    # 3.1.x forced --disable-gpu on both browser engines. That is not universal:
    # some current WebView2/Chromium paths render an all-black surface when forced
    # into that path. Keep GPU selection native by default and expose explicit fallbacks.
    legacy = os.environ.get('FUSION_BROWSER_DISABLE_GPU')
    legacy_value = None if legacy is None else legacy.strip().lower() in {'1','y','yes','true','on'}

    if varname == 'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':
        disable = bool_env('FUSION_WEBVIEW2_DISABLE_GPU', legacy_value if legacy_value is not None else False)
        sandbox = bool_env('FUSION_WEBVIEW2_NO_SANDBOX', True)
    elif varname == 'QTWEBENGINE_CHROMIUM_FLAGS':
        disable = bool_env('FUSION_QTWEBENGINE_DISABLE_GPU', legacy_value if legacy_value is not None else False)
        sandbox = bool_env('FUSION_QTWEBENGINE_NO_SANDBOX', False)
    else:
        disable = legacy_value if legacy_value is not None else False
        sandbox = False
    return disable, sandbox


if __name__ == '__main__':
    name = sys.argv[1]
    disable_gpu, no_sandbox = policy(name)
    print(flags(os.environ.get(name, ''), disable_gpu, no_sandbox))
