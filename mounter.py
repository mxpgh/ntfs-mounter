import os
import shutil
import subprocess


def _check_macfuse() -> bool:
    """Check if macFUSE is installed on the system.

    macOS 13+ removed Apple's built-in mount_ntfs, so ntfs-3g (via macFUSE)
    is the only option. This checks for the macFUSE filesystem bundle.
    """
    macfuse_bundle = "/Library/Filesystems/macfuse.fs"
    if os.path.exists(macfuse_bundle):
        return True
    # Also check via mount_macfuse in PATH
    if shutil.which("mount_macfuse"):
        return True
    return False


def _find_mount_ntfs() -> str | None:
    """Locate the NTFS mount command — try Apple's native, then ntfs-3g.

    macOS 13+ (Ventura) removed /sbin/mount_ntfs entirely.
    On those systems only ntfs-3g (with macFUSE) works.
    """
    for candidate in ["ntfs-3g",
                       "/usr/local/bin/mount_ntfs",
                       "/opt/homebrew/sbin/mount_ntfs",
                       "/usr/local/sbin/mount_ntfs",
                       "/sbin/mount_ntfs"]:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _sudo(commands: list[str]) -> tuple[bool, str]:
    """Run shell commands as root via sudo -S, no temp files."""
    apple = (
        'display dialog "请输入管理员密码"'
        ' with title "NTFS Mounter"'
        ' default answer "" with hidden answer with icon caution'
    )
    pw_p = subprocess.run(
        ["osascript", "-e", apple],
        capture_output=True, text=True, timeout=60,
    )
    if pw_p.returncode != 0:
        return False, "已取消"

    password = ""
    for part in pw_p.stdout.split(","):
        if "text returned:" in part:
            password = part.split(":", 1)[1].strip()
            break
    if not password:
        return False, "已取消"

    script = " && ".join(commands)
    p = subprocess.run(
        ["sudo", "-S", "/bin/bash", "-c", script],
        input=password + "\n",
        capture_output=True, text=True, timeout=30,
    )
    return p.returncode == 0, p.stderr.strip()


def mount_ntfs_readwrite(device: str, label: str) -> tuple[bool, str, str]:
    """Unmount, then re-mount an NTFS volume as read-write."""
    mount_point = f"/tmp/ntfs-{label}"

    mount_cmd = _find_mount_ntfs()
    if not mount_cmd:
        return False, "未找到 NTFS 驱动", mount_point

    # macOS 13+ 使用 ntfs-3g 时需要 macFUSE
    if "ntfs-3g" in mount_cmd and not _check_macfuse():
        return False, "缺少 macFUSE", mount_point

    ok, out = _sudo([
        f"diskutil unmount {device}",
        f"mkdir -p {mount_point}",
        f"{mount_cmd} -o rw,nobrowse,windows_names,hide_dot_files,hide_hid_files,allow_other,auto_xattr,local {device} {mount_point}",
    ])

    if not ok:
        subprocess.run(["diskutil", "mount", device], capture_output=True, timeout=15)
        err = "已取消" if "cancel" in out.lower() or "user canceled" in out.lower() else "挂载失败"
        return False, err, mount_point

    return True, "", mount_point


def unmount_volume(device: str) -> tuple[bool, str]:
    """Safely unmount, then restore to standard /Volumes mount."""
    ok, out = _sudo([f"diskutil unmount {device}"])
    if not ok:
        return False, "卸载失败"
    subprocess.run(["diskutil", "mount", device], capture_output=True, timeout=15)
    return True, ""


def check_volume_busy(mount_point: str) -> list[str]:
    try:
        p = subprocess.run(
            ["lsof", "+D", mount_point],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0 and p.stdout.strip():
            return [l for l in p.stdout.split("\n")[1:] if l.strip()]
        return []
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def check_windows_hibernation(device: str) -> bool:
    try:
        p = subprocess.run(
            ["diskutil", "info", "-plist", device],
            capture_output=True, text=False, timeout=15,
        )
        if p.returncode != 0:
            return False
        import plistlib
        return plistlib.loads(p.stdout).get("Hibernated", False)
    except (subprocess.TimeoutExpired, ValueError):
        return False
