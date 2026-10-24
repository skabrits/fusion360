#!/usr/bin/env python3
"""Apply Fusion's per-window X11 policy to a Staging-patched Wine tree.

The policy is deliberately not "manage everything" or "unmanage everything":
Fusion needs its main frame and dock/palette toolwindows managed by the host WM,
while modal/dialog/layered surfaces must remain in Wine's Win32 stacking domain.
"""
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one {label} anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply(root: Path) -> None:
    drv = root / "dlls" / "winex11.drv"
    header = drv / "x11drv.h"
    main = drv / "x11drv_main.c"
    window = drv / "window.c"
    for path in (header, main, window):
        if not path.is_file():
            raise SystemExit(f"Wine source file missing: {path}")

    replace_once(
        header,
        "extern BOOL managed_mode;\n",
        "extern BOOL managed_mode;\n"
        "extern BOOL unmanage_owned_windows;\n"
        "extern BOOL fusion_window_policy;\n",
        "managed_mode declaration",
    )

    replace_once(
        main,
        "BOOL managed_mode = TRUE;\n",
        "BOOL managed_mode = TRUE;\n"
        "BOOL unmanage_owned_windows = FALSE;\n"
        "BOOL fusion_window_policy = FALSE;\n",
        "managed_mode definition",
    )

    replace_once(
        main,
        '    if (!get_config_key( hkey, appkey, "Managed", buffer, sizeof(buffer) ))\n'
        '        managed_mode = IS_OPTION_TRUE( buffer[0] );\n',
        '    if (!get_config_key( hkey, appkey, "Managed", buffer, sizeof(buffer) ))\n'
        '        managed_mode = IS_OPTION_TRUE( buffer[0] );\n'
        '    if (!get_config_key( hkey, appkey, "UnmanageOwnedWindows", buffer, sizeof(buffer) ))\n'
        '        unmanage_owned_windows = IS_OPTION_TRUE( buffer[0] );\n'
        '    if (!get_config_key( hkey, appkey, "FusionWindowPolicy", buffer, sizeof(buffer) ))\n'
        '        fusion_window_policy = IS_OPTION_TRUE( buffer[0] );\n',
        "Managed option",
    )

    replace_once(
        window,
        "    /* child windows are not managed */\n"
        "    style = NtUserGetWindowLongW( hwnd, GWL_STYLE );\n"
        "    if ((style & (WS_CHILD|WS_POPUP)) == WS_CHILD) return FALSE;\n",
        "    /* child windows are not managed */\n"
        "    style = NtUserGetWindowLongW( hwnd, GWL_STYLE );\n"
        "    if ((style & (WS_CHILD|WS_POPUP)) == WS_CHILD) return FALSE;\n"
        "\n"
        "    ex_style = NtUserGetWindowLongW( hwnd, GWL_EXSTYLE );\n"
        "\n"
        "    /* 3.1.x compatibility. The 3.2 policy supersedes this coarse rule. */\n"
        "    if (!fusion_window_policy && unmanage_owned_windows &&\n"
        "        NtUserGetWindowRelative( hwnd, GW_OWNER ))\n"
        "        return FALSE;\n"
        "\n"
        "    /*\n"
        "     * Fusion window policy. Do not use WS_DLGFRAME alone as a dialog\n"
        "     * test: WS_CAPTION includes it, so ordinary titled application\n"
        "     * frames would otherwise become unmanaged.\n"
        "     */\n"
        "    if (fusion_window_policy)\n"
        "    {\n"
        "        HWND owner = NtUserGetWindowRelative( hwnd, GW_OWNER );\n"
        "        BOOL captioned = (style & WS_CAPTION) == WS_CAPTION;\n"
        "        BOOL resizable = (style & WS_THICKFRAME) != 0;\n"
        "        BOOL app_window = (ex_style & WS_EX_APPWINDOW) != 0;\n"
        "\n"
        "        /* Primary/unowned application frames must always stay managed. */\n"
        "        if (!owner && (resizable || app_window || captioned)) return TRUE;\n"
        "\n"
        "        /* Composition dimmers/transparent helpers stay in Wine stacking. */\n"
        "        if ((ex_style & WS_EX_LAYERED) && !resizable && !app_window) return FALSE;\n"
        "\n"
        "        /* Explicit owned modal dialogs stay with their owner. */\n"
        "        if (owner && (ex_style & WS_EX_DLGMODALFRAME)) return FALSE;\n"
        "\n"
        "        /* Floating palettes are tools, not modal sheets. */\n"
        "        if (owner && (ex_style & WS_EX_TOOLWINDOW) &&\n"
        "            !(style & WS_SYSMENU) && !(ex_style & WS_EX_LAYERED)) return TRUE;\n"
        "\n"
        "        /* Fusion/Qt modal sheets are commonly owned, fixed-size popups. */\n"
        "        if (owner && (style & WS_POPUP) && !resizable) return FALSE;\n"
        "\n"
        "        /* Resizable/app-style auxiliary frames remain host-managed. */\n"
        "        if (resizable || app_window || captioned) return TRUE;\n"
        "    }\n",
        "child-window management block",
    )

    checks = {
        header: "extern BOOL fusion_window_policy;",
        main: 'get_config_key( hkey, appkey, "FusionWindowPolicy"',
        window: "Primary/unowned application frames must always stay managed.",
    }
    for path, needle in checks.items():
        if needle not in path.read_text(encoding="utf-8"):
            raise SystemExit(f"Wine transform verification failed for {path}: {needle}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} WINE_SOURCE_ROOT")
    apply(Path(sys.argv[1]))
