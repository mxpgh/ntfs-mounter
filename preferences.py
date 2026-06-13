import os
import json
import rumps

# Preferences stored in ~/.ntfs-mounter/prefs.json
PREFS_DIR = os.path.expanduser("~/.ntfs-mounter")
PREFS_FILE = os.path.join(PREFS_DIR, "prefs.json")
LAUNCH_AGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
LAUNCH_AGENT_PLIST = os.path.join(LAUNCH_AGENT_DIR, "com.ntfs-mounter.plist")


DEFAULTS = {
    "auto_mount": False,       # Auto-mount NTFS on detection
    "launch_at_login": False,  # Start app on login
    "disclaimer_accepted": False,
}


def load_prefs() -> dict:
    try:
        with open(PREFS_FILE) as f:
            prefs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        prefs = {}
    return {**DEFAULTS, **prefs}


def save_prefs(prefs: dict):
    os.makedirs(PREFS_DIR, exist_ok=True)
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


def set_launch_at_login(enabled: bool):
    """Enable or disable launch at login via LaunchAgent."""
    import subprocess
    os.makedirs(LAUNCH_AGENT_DIR, exist_ok=True)
    if enabled:
        import sys
        app_path = os.path.abspath(os.path.join(sys.executable, "..", "..", ".."))
        if not app_path.endswith(".app"):
            app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        plist = {
            "Label": "com.ntfs-mounter",
            "ProgramArguments": ["/usr/bin/open", "-a", app_path],
            "RunAtLoad": True,
            "KeepAlive": False,
        }
        import plistlib
        with open(LAUNCH_AGENT_PLIST, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(
            ["launchctl", "load", "-w", LAUNCH_AGENT_PLIST],
            capture_output=True, timeout=10,
        )
    else:
        subprocess.run(
            ["launchctl", "unload", "-w", LAUNCH_AGENT_PLIST],
            capture_output=True, timeout=10,
        )
        try:
            os.remove(LAUNCH_AGENT_PLIST)
        except FileNotFoundError:
            pass


class PreferencesWindow:
    """Simple preferences window using rumps-alert style settings."""

    def __init__(self, app):
        self.app = app
        self.prefs = load_prefs()

    def show(self):
        """Show the preferences / about dialog."""
        macos_ver = os.popen("sw_vers -productVersion").read().strip()
        use_ntfs3g = macos_ver and tuple(int(x) for x in macos_ver.split(".")) >= (13,)
        driver_name = "ntfs-3g + macFUSE" if use_ntfs3g else "Apple mount_ntfs"
        msg = (
            "NTFS Mounter v1.1\n\n"
            f"macOS {macos_ver}\n"
            f"驱动: {driver_name}\n\n"
            "macOS 13+ 已移除 Apple 原生 mount_ntfs。\n"
            "本工具自动使用 ntfs-3g + macFUSE 方案。\n\n"
            "⚠️ 免责声明\n"
            "NTFS 第三方写入可能带来数据损坏风险。\n"
            "请勿用于存储重要数据。\n\n"
            "使用本工具即表示您已了解并接受此风险。"
        )
        rumps.alert(
            title="NTFS Mounter",
            message=msg,
            ok="我知道了",
        )

        # Mark disclaimer as accepted on first view
        if not self.prefs.get("disclaimer_accepted"):
            self.prefs["disclaimer_accepted"] = True
            save_prefs(self.prefs)
