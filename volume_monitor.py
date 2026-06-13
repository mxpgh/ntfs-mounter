import plistlib
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class NTFSVolume:
    device: str
    label: str
    mount_point: str
    size_bytes: int
    free_bytes: int
    writable: bool
    hibernated: bool


def _find_ntfs_volumes() -> list[NTFSVolume]:
    volumes: list[NTFSVolume] = []

    try:
        p = subprocess.run(
            ["diskutil", "list"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return volumes

    ntfs_disks = []
    for line in p.stdout.split("\n"):
        if "Windows_NTFS" in line or "Microsoft Basic Data" in line:
            parts = line.split()
            if parts:
                disk_id = parts[-1]
                if disk_id.startswith("disk") and "s" in disk_id:
                    ntfs_disks.append(f"/dev/{disk_id}")

    for device in ntfs_disks:
        try:
            p2 = subprocess.run(
                ["diskutil", "info", "-plist", device],
                capture_output=True, text=False, timeout=10,
            )
            if p2.returncode != 0:
                continue

            plist = plistlib.loads(p2.stdout)
            if plist.get("FilesystemType", "").lower() != "ntfs":
                continue

            volumes.append(NTFSVolume(
                device=device,
                label=plist.get("VolumeName", "Untitled"),
                mount_point=plist.get("MountPoint", ""),
                size_bytes=plist.get("Size", 0),
                free_bytes=plist.get("FreeSpace", 0),
                writable=plist.get("Writable", False),
                hibernated=plist.get("Hibernated", False),
            ))
        except (subprocess.TimeoutExpired, OSError, ValueError):
            continue

    return volumes


class VolumeMonitor:
    """Monitors NTFS volumes with polling and change callbacks."""

    def __init__(self, poll_interval: float = 5.0):
        self._interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._volumes: dict[str, NTFSVolume] = {}

        self.on_change: Callable[[list[NTFSVolume]], None] | None = None

    @property
    def volumes(self) -> list[NTFSVolume]:
        with self._lock:
            return list(self._volumes.values())

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def refresh_now(self):
        t = threading.Thread(target=self._scan, daemon=True)
        t.start()

    def _poll_loop(self):
        while self._running:
            try:
                self._scan()
            except Exception:
                pass
            time.sleep(self._interval)

    def _scan(self):
        try:
            current = _find_ntfs_volumes()
        except Exception:
            return

        callback = None
        cb_volumes = []

        with self._lock:
            current_map = {v.device: v for v in current}
            previous_map = dict(self._volumes)
            changed = False

            for dev, vol in current_map.items():
                prev = previous_map.get(dev)
                if prev is None or self._volume_changed(prev, vol):
                    changed = True
                    break

            for dev in previous_map:
                if dev not in current_map:
                    changed = True
                    break

            self._volumes = current_map

            if changed and self.on_change:
                callback = self.on_change
                cb_volumes = list(self._volumes.values())

        if callback:
            try:
                callback(cb_volumes)
            except Exception:
                pass

    @staticmethod
    def _volume_changed(a: NTFSVolume, b: NTFSVolume) -> bool:
        return (
            a.writable != b.writable
            or a.mount_point != b.mount_point
            or a.label != b.label
            or a.hibernated != b.hibernated
            or a.size_bytes != b.size_bytes
            or a.free_bytes != b.free_bytes
        )


def setup_disk_arbitration_callback(on_disk_event: Callable[[], None]):
    try:
        from Foundation import NSObject
        from DiskArbitration import (
            DASessionCreate,
            DARegisterDiskAppearedCallback,
            DARegisterDiskDisappearedCallback,
            DARegisterDiskDescriptionChangedCallback,
            DASessionScheduleWithRunLoop,
        )
        from CoreFoundation import CFRunLoopGetCurrent, kCFRunLoopDefaultMode

        session = DASessionCreate(None)
        if session is None:
            return

        def callback(session, disk, context):
            on_disk_event()

        DARegisterDiskAppearedCallback(session, None, callback, None)
        DARegisterDiskDisappearedCallback(session, None, callback, None)
        DARegisterDiskDescriptionChangedCallback(session, None, None, callback, None)

        rl = CFRunLoopGetCurrent()
        DASessionScheduleWithRunLoop(session, rl, kCFRunLoopDefaultMode)

        return session
    except ImportError:
        return None
