#!/usr/bin/env python3
"""NTFS Mounter — macOS menu bar app for NTFS read-write access."""

import sys
import os

# Add project dir to path for PyInstaller compatibility
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import NTFSMounterApp
from preferences import load_prefs, DEFAULTS


def ensure_dependencies():
    """Check that required system commands are available."""
    from mounter import _find_mount_ntfs, _check_macfuse
    mount_cmd = _find_mount_ntfs()
    if not mount_cmd:
        from rumps import alert
        alert(
            title="错误",
            message="找不到 NTFS 驱动。\n\n"
                    "macOS 13+ 不再自带 mount_ntfs，\n"
                    "请安装 macFUSE + ntfs-3g：\n"
                    "  brew install --cask macfuse\n"
                    "  brew tap gromgit/homebrew-fuse && brew install ntfs-3g-mac\n"
                    "或从 https://macfuse.io 下载安装。",
            ok="退出",
        )
        sys.exit(1)

    # ntfs-3g 需要 macFUSE 内核扩展支持
    if "ntfs-3g" in mount_cmd and not _check_macfuse():
        from rumps import alert
        alert(
            title="错误",
            message="找到 ntfs-3g 但缺少 macFUSE。\n\n"
                    "请安装 macFUSE：\n"
                    "  brew install --cask macfuse\n"
                    "或从 https://macfuse.io 下载安装。\n\n"
                    "安装后需重启电脑。",
            ok="退出",
        )
        sys.exit(1)

    if not os.path.exists("/usr/sbin/diskutil"):
        from rumps import alert
        alert(title="错误", message="找不到 diskutil，请确认运行环境。", ok="退出")
        sys.exit(1)


def main():
    ensure_dependencies()

    # Load preferences
    prefs = load_prefs()

    # Auto-start launch agent if enabled
    if prefs.get("launch_at_login"):
        from preferences import set_launch_at_login
        set_launch_at_login(True)

    # Show disclaimer on first run
    if not prefs.get("disclaimer_accepted"):
        from preferences import PreferencesWindow
        PreferencesWindow(None).show()

    app = NTFSMounterApp()
    app.run()


if __name__ == "__main__":
    main()
