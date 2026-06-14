# NTFS Mounter 代码审查

审查时间：2026/06/02

覆盖文件：`mounter.py`, `ntfs_mounter.py`, `ui.py`, `preferences.py`, `volume_monitor.py`, `NTFS Mounter.spec`, `build.sh`

---

## 🔴 严重

### 1. Hibernation 弹窗结果被忽略

**文件** `ui.py:29-40`

```python
if vol.hibernated or check_windows_hibernation(device):
    rumps.alert(...)  # 返回值被忽略
# 无论用户点"继续"还是"取消"，挂载都继续执行
```

`rumps.alert()` 返回用户点击的按钮文字，但返回值未被捕获判断。用户选择"取消"后，读写挂载依然会执行，存在数据损坏风险。

### 2. 后台线程操作 GUI

**文件** `ui.py:19-21, 66-68`

`_do_mount` 和 `_do_eject` 在 daemon 线程中执行，但 `rumps.alert()` 依赖 AppKit，必须在主线程调用。macOS 上后台线程操作 GUI 可能导致崩溃或未定义行为。

---

## 🟠 高风险

### 3. `diskutil info` 解析强依赖英文 locale，中文系统静默失效

**文件** `volume_monitor.py:72-78`、`mounter.py:108-122`

```python
info.get("volume_name", "Untitled")   # 中文系统 -> key 是 "卷名称"
info.get("read-only_media", "yes")    # 中文系统 -> "只读介质"
info.get("writable", "no")            # 中文系统 -> "可写入"
```

在非英文 macOS 上，所有 key 匹配不到，导致卷标永远 "Untitled"、挂载点/大小/可写性全部解析失败，整个 app 不可用。

### 4. `run_as_admin` 超时未处理

**文件** `mounter.py:13-17`

```python
p = subprocess.run(
    ["osascript", "-e", script],
    capture_output=True, text=True, timeout=60,
)
```

`mount_ntfs_readwrite` 和 `unmount_volume` 直接调用 `run_as_admin` 但没有 try/except。用户在密码框超时（60秒）会抛出 `TimeoutExpired`，导致整个 app 崩溃。其他函数（`check_volume_busy`, `get_volume_info`）则正确捕获了此异常。

### 5. 直接访问 monitor 的私有属性

**文件** `ui.py:143`

```python
def _update_title(self):
    with self.monitor._lock:          # 应使用 self.monitor.volumes
        count = len(self.monitor._volumes)
```

`VolumeMonitor` 已经提供了 `volumes` property 封装锁逻辑。直接访问 `_lock` 和 `_volumes` 破坏封装，后续修改 `VolumeMonitor` 内部实现时容易出问题。

---

## 🟡 中风险

### 6. `lsof` 异常传播到后台线程

**文件** `ui.py:44-47`

`check_volume_busy` 仅捕获了 `TimeoutExpired`，`_do_mount` 调用它时也没有额外 try/except。如果 `lsof` 抛出其他异常（如权限不足），daemon 线程静默退出。

### 7. LaunchAgent 路径计算脆弱

**文件** `preferences.py:41-44`

```python
app_path = os.path.abspath(os.path.join(sys.executable, "..", "..", ".."))
```

从 PyInstaller 捆绑二进制向 `.app` 根目录回溯依赖三层 `..`，打包结构变化时路径错误，开机启动会静默失败。

### 8. 快速调用 `show_status` 产生重复定时器

**文件** `ui.py:122-127`

```python
def show_status(self, text: str):
    self.title = text[:30]
    if self._status_timer:
        self._status_timer = None    # 旧 timer 仍在运行
    self._status_timer = rumps.Timer(self._reset_title, 4)
    self._status_timer.start()
```

旧 timer 只置空引用但未 stop/ cancel，快速连续调用会生成多个活跃 timer，4 秒后将标题错误重置。

### 9. 恢复只读后 UI 显示"挂载失败"

**文件** `mounter.py:51-53`

```python
run_as_admin(["diskutil", "mount", device])  # 已恢复只读
return False, f"挂载为读写失败: {err}\n已恢复为只读模式"
```

失败时磁盘实际已恢复为只读可用状态，但返回 `False` 导致 UI 弹"挂载失败"——用户以为磁盘坏了，体验不好。

### 10. 无日志系统

所有挂载/卸载/错误事件都没有落盘日志，用户反馈问题时无法排查。

---

## 🟢 低风险 / 建议

| # | 问题 | 位置 |
|---|------|------|
| 11 | `setup_disk_arbitration_callback` 已实现但从未被调用，`refresh_now` 也未使用 | `volume_monitor.py:190-225` |
| 12 | Daemon 线程在 mount/eject 进行中时 app 退出会导致操作中断 | `ui.py:19, 66` |
| 13 | `os.path.exists` 不检查可执行权限 | `ntfs_mounter.py:18` |
| 14 | `lsof +D` 输出解析依赖列位置，不同 macOS 版本格式可能不一致 | `mounter.py:79-81` |
| 15 | `optimize=0` 打包时 Python 字节码优化未开启 | `NTFS Mounter.spec:15` |
| 16 | 无 icon，菜单栏纯文字显示 | `NTFS Mounter.spec:48` |

---

## 优先修复建议

1. **#1 — Hibernation 弹窗**：捕获 `rumps.alert` 返回值，用户点"取消"时 `return`
2. **#3 — locale 兼容性**：对 `diskutil info` 输出用 `locale` 模块或同时匹配中英文 key，或用 plist 格式输出（`-plist` flag）
3. **#4 — 超时崩溃**：在 `mount_ntfs_readwrite` 和 `unmount_volume` 中捕获 `TimeoutExpired`
4. **#2 — 后台线程 GUI**：用 `rumps.timer` 或主线程队列调度弹窗
