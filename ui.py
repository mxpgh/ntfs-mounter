import threading
import webbrowser
import rumps

from volume_monitor import VolumeMonitor, NTFSVolume
from mounter import mount_ntfs_readwrite, unmount_volume


# --- Menu callbacks ---------------------------------------------------------

def _make_mount_callback(vol: NTFSVolume, app: "NTFSMounterApp"):
    def callback(sender):
        app.show_working(f"正在挂载 {vol.label}...")
        t = threading.Thread(target=_do_mount_worker, args=(vol, app), daemon=True)
        t.start()
    return callback


def _do_mount_worker(vol: NTFSVolume, app: "NTFSMounterApp"):
    ok, err, mount_path = mount_ntfs_readwrite(vol.device, vol.label)
    if ok:
        app._enqueue(lambda: app.show_status(f"「{vol.label}」已挂载为读写"))
        # Update the volume's mount_point so Finder opens the right place
        vol.mount_point = mount_path
        app.monitor.refresh_now()
    elif "未找到 NTFS 驱动" in err:
        app._enqueue(lambda: rumps.alert(
            title="缺少 NTFS 驱动",
            message="macOS 13+ 不再自带 NTFS 读写驱动。\n\n"
                    "请安装 macFUSE + ntfs-3g：\n"
                    "  brew install --cask macfuse\n"
                    "  brew tap gromgit/homebrew-fuse && brew install ntfs-3g-mac\n"
                    "或从 https://macfuse.io 下载。",
        ))
        app._enqueue(lambda: app.show_status("缺少 NTFS 驱动"))
    elif "缺少 macFUSE" in err:
        app._enqueue(lambda: rumps.alert(
            title="缺少 macFUSE",
            message="已找到 ntfs-3g，但缺少 macFUSE 内核扩展。\n\n"
                    "请安装 macFUSE：\n"
                    "  brew install --cask macfuse\n"
                    "安装后需重启电脑才能生效。\n\n"
                    "或从 https://macfuse.io 下载安装。",
        ))
        app._enqueue(lambda: app.show_status("缺少 macFUSE"))
    else:
        app._enqueue(lambda: rumps.alert(title="无法挂载为读写", message=err))
        app._enqueue(lambda: app.show_status(f"「{vol.label}」保持只读"))


def _make_open_finder_callback(vol: NTFSVolume):
    def callback(sender):
        mp = vol.mount_point or f"/Volumes/{vol.label}"
        webbrowser.open(f"file://{mp}")
    return callback


def _make_eject_callback(vol: NTFSVolume, app: "NTFSMounterApp"):
    def callback(sender):
        app.show_working(f"正在移除 {vol.label}...")
        t = threading.Thread(target=_do_eject_worker, args=(vol, app), daemon=True)
        t.start()
    return callback


def _do_eject_worker(vol: NTFSVolume, app: "NTFSMounterApp"):
    ok, err = unmount_volume(vol.device)
    if ok:
        app._enqueue(lambda: app.show_status(f"「{vol.label}」已安全移除，可拔出磁盘"))
        app.monitor.refresh_now()
    else:
        app._enqueue(lambda: rumps.alert(title="卸载失败", message=err))
        app._enqueue(lambda: app.show_status(f"「{vol.label}」卸载失败"))


# --- Menu building ----------------------------------------------------------

def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1000**4:
        return f"{size_bytes / 1000**4:.1f} TB"
    if size_bytes >= 1000**3:
        return f"{size_bytes / 1000**3:.0f} GB"
    if size_bytes >= 1000**2:
        return f"{size_bytes / 1000**2:.0f} MB"
    return f"{size_bytes} B"


def _format_free(free_bytes: int, total_bytes: int) -> str:
    if total_bytes == 0:
        return ""
    if free_bytes >= 1000**3:
        return f"可用 {free_bytes / 1000**3:.0f} GB"
    return f"可用 {free_bytes / 1000**2:.0f} MB"


# --- The rumps App ----------------------------------------------------------

class NTFSMounterApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="NTFS",
            title="NTFS",
            icon=None,
            quit_button=None,
        )
        self.monitor = VolumeMonitor(poll_interval=5.0)
        self.monitor.on_change = self._on_volumes_changed

        self._status_timer: rumps.Timer | None = None

        # Message queue for bg threads → main thread dispatch
        self._msg_lock = threading.Lock()
        self._msg_queue: list = []
        rumps.Timer(self._drain_messages, 0.2).start()

        self._rebuild_menu([])
        self.monitor.start()

    # --- Background-thread-safe message dispatch ---

    def _enqueue(self, fn):
        with self._msg_lock:
            self._msg_queue.append(fn)

    def _drain_messages(self, timer):
        with self._msg_lock:
            batch = self._msg_queue
            self._msg_queue = []
        for fn in batch:
            try:
                fn()
            except Exception:
                pass

    # --- UI helpers (call from main thread only) ---

    def show_status(self, text: str):
        self.title = text[:30]
        if self._status_timer:
            self._status_timer.stop()
        self._status_timer = rumps.Timer(self._reset_title, 4)
        self._status_timer.start()

    def show_working(self, text: str):
        self.title = text[:30]

    def _reset_title(self, _timer=None):
        self._update_title()
        self._status_timer = None

    # --- Volume change handling ---

    def _on_volumes_changed(self, volumes: list[NTFSVolume]):
        # Called from VolumeMonitor's poll thread — enqueue to main thread
        self._enqueue(lambda: self._rebuild_menu(volumes) or self._update_title())

    def _update_title(self):
        count = len(self.monitor.volumes)
        if count == 0:
            self.title = "NTFS"
        else:
            self.title = f"N:{count}"

    def _rebuild_menu(self, volumes: list[NTFSVolume]):
        items = []

        if not volumes:
            items.append(rumps.MenuItem("未检测到 NTFS 磁盘", callback=None))
        else:
            for vol in volumes:
                status_icon = "✏️" if vol.writable else "🔒"
                size_str = _format_size(vol.size_bytes)
                free_str = _format_free(vol.free_bytes, vol.size_bytes)

                label = f"{status_icon}  {vol.label}  ({size_str})"
                vol_menu = rumps.MenuItem(label)

                if vol.writable:
                    vol_menu.add(rumps.MenuItem(
                        "📂 在 Finder 中打开",
                        callback=_make_open_finder_callback(vol),
                    ))
                    vol_menu.add(rumps.MenuItem(
                        "⏏  安全移除",
                        callback=_make_eject_callback(vol, self),
                    ))
                else:
                    vol_menu.add(rumps.MenuItem(
                        "🔓 挂载为读写",
                        callback=_make_mount_callback(vol, self),
                    ))

                if free_str:
                    vol_menu.add(rumps.separator)
                    vol_menu.add(rumps.MenuItem(free_str, callback=None))

                items.append(vol_menu)

        items.append(rumps.separator)
        items.append(rumps.MenuItem("偏好设置...", callback=self._open_preferences))
        items.append(None)
        items.append(rumps.MenuItem("退出", callback=self._quit))

        self.menu.clear()
        self.menu.update(items)

    def _open_preferences(self, sender):
        from preferences import PreferencesWindow
        PreferencesWindow(self).show()

    def _quit(self, sender):
        self.monitor.stop()
        rumps.quit_application()
