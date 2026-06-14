# NTFS Mounter 代码审查（自动化扫描）

审查时间：2026/06/02  
审查方式：`/code-review` 高召回模式（7 角度 × 6 候选 → 验证去重 → 取 Top 10）  
覆盖文件：`mounter.py`, `ntfs_mounter.py`, `ui.py`, `preferences.py`, `volume_monitor.py`

---

## 🔴 致命

### 1. `_scan` 死锁：非可重入 Lock 导致检测首个卷变化即永久冻结

**文件** `volume_monitor.py:142`

```
_scan() 内 with self._lock:
    ...
    if changed:
        self._volumes = current_map
        if self.on_change:
            self.on_change(self.volumes)   ← self.volumes 求值再次 acquire(self._lock)
```

`self._lock = threading.Lock()`（非可重入）。`volumes` property 使用 `with self._lock:`。`_scan` 在持有锁的块内求值 `self.volumes` → 同一线程第二次 acquire → **永久阻塞**。

调用链：`_scan` → `on_change` → `_on_volumes_changed` → `_update_title` → `self.monitor.volumes` → 再次 acquire。

**后果**：首个卷变化触发即死锁，轮询线程永久阻塞，菜单栏冻结，后续所有 volume 检测停止。 `_update_title`（`ui.py:143`）从主线程访问 `self.monitor.volumes` 同样会阻塞，app 标题栏也一起冻结。

---

## 🟠 高风险

### 2. Hibernation 弹窗结果被忽略

**文件** `ui.py:30`

```python
if vol.hibernated or check_windows_hibernation(device):
    rumps.alert(
        title="Windows 休眠检测",
        message=...,
        ok="继续挂载",
        cancel="取消",
    )
    # 返回值未被捕获判断，挂载继续执行
```

`rumps.alert` 返回用户点击的按钮文字，代码完全忽略。用户选择"取消"后读写挂载依然执行。

**后果**：Windows 休眠状态下写入 NTFS 文件系统存在数据损坏风险，用户的取消意图被忽略。

---

### 3. 后台 daemon 线程操作 GUI（AppKit 线程违规）

**文件** `ui.py:19-21, 66-68`

`_do_mount` 和 `_do_eject` 在 `threading.Thread(daemon=True)` 中执行，直接调用：
- `rumps.alert()` — 依赖 AppKit NSAlert
- `app.show_status()` / `app.show_working()` — 修改 `self.title`
- `app.show_status("已安全移除")` 等

`_on_volumes_changed` 从轮询线程调用 `_rebuild_menu`，修改 `self.menu`（NSMenu）。

**后果**：macOS AppKit 不允许非主线程操作 UI。可能导致随机崩溃、菜单项错乱、对话框无响应。快速插拔/密集点击时触发概率更高。

---

### 4. 读写挂载失败后恢复路径异常未被捕获

**文件** `mounter.py:51-56`

```python
# mount_ntfs 失败后的恢复
run_as_admin(["diskutil", "mount", device])   # 返回值和异常都被忽略
return False, f"挂载为读写失败: {err}\n已恢复为只读模式"
```

两个问题：
- `run_as_admin` 使用 `subprocess.run(timeout=60)`，用户在 macOS 授权对话框超时（60s）则抛出 `subprocess.TimeoutExpired`，无 try/except 包裹
- 恢复命令本身的返回码和 stderr 完全被忽略

超时异常传播路径：`mount_ntfs_readwrite` → `_do_mount`（无 try/except）→ daemon 线程静默死亡。用户界面永远停留在"正在挂载..."状态。

---

## 🟡 中风险

### 5. `on_change` 回调无异常保护，任一异常杀死轮询线程

**文件** `volume_monitor.py:174`

```python
def _scan(self):
    try:
        current = _find_ntfs_volumes()   # 仅这一行在 try/except 内
    except Exception:
        return
    # ... 后续代码包括 on_change 调用均无保护
    if changed:
        self._volumes = current_map
        if self.on_change:
            self.on_change(self.volumes)  # 抛异常则杀死线程
```

`_poll_loop` 同样无 try/except：

```python
def _poll_loop(self):
    while self._running:
        self._scan()         # 无保护
        time.sleep(self._interval)
```

**后果**：rumps 菜单重建或其他回调抛异常 → 通过 `_scan` → `_poll_loop` 传播，daemon 线程静默死亡。VolumeMonitor 永久停止，菜单栏展示陈旧快照不再更新。

---

### 6. `set_launch_at_login(False)` 不卸载 LaunchAgent

**文件** `preferences.py:55-59`

```python
else:  # 禁用
    try:
        os.remove(LAUNCH_AGENT_PLIST)    # 仅删除文件！
    except FileNotFoundError:
        pass
```

不调用 `launchctl unload`。plist 被删除但 launchd 仍持有内存注册。

启用路径（`set_launch_at_login(True)`）也只写 plist 不调用 `launchctl load`。

**后果**：
- 禁用后：进程继续运行至会话结束，重启登录后才真正禁用
- 启用后：新 plist 写入 `~/Library/LaunchAgents/` 但当前登录会话中无效，需下次登录才生效

---

### 7. `_volume_changed` 未比较 `size_bytes` 和 `free_bytes`

**文件** `volume_monitor.py:148`

```python
@staticmethod
def _volume_changed(a: NTFSVolume, b: NTFSVolume) -> bool:
    return (
        a.writable != b.writable
        or a.mount_point != b.mount_point
        or a.label != b.label
        or a.hibernated != b.hibernated
        # ← 缺少 size_bytes 和 free_bytes
    )
```

自由空间变化不视为"变化"触发 `on_change`，UI 菜单栏展示陈旧可用空间值。

**后果**：用户写入/删除文件后，菜单栏显示（如"可用 50 GB"）与实际不符，直到其他属性变化触发菜单重建。

---

### 8. 快速调用 `show_status` 产生并发定时器

**文件** `ui.py:122-127`

```python
def show_status(self, text: str):
    self.title = text[:30]
    if self._status_timer:
        self._status_timer = None       # 置空引用但未 stop 旧 timer！
    self._status_timer = rumps.Timer(self._reset_title, 4)
    self._status_timer.start()
```

`rumps.Timer` 底层是 `NSTimer`，`self._status_timer = None` 不会使旧 timer invalidate。

**后果**：快速连续调用产生多个活跃 timer，4 秒后旧 timer 触发 `_reset_title` 将标题错误重置。

---

### 9. 免责声明仅在首次打开偏好设置时弹出

**文件** `ntfs_mounter.py:40`

```python
if not prefs.get("disclaimer_accepted"):
    from preferences import PreferencesWindow
    # 只 import 了但没调用 .show()！
```

注释说 "Will show on first preferences open"，但这是用户手动打开偏好设置时的副作用，不是自动展示。

**后果**：新用户直接挂载 NTFS 磁盘，从未看到「mount_ntfs -o rw 非 Apple 官方支持路径，可能数据损坏」的提示。

---

### 10. 死代码：`get_volume_info()` 和 `setup_disk_arbitration_callback()` 从未被调用

**文件** `mounter.py:103`、`volume_monitor.py:190`

| 函数 | 行数 | 用途 | 调用点 |
|------|------|------|--------|
| `get_volume_info()` | 15 行 | 解析 `diskutil info -plist` | 零 |
| `setup_disk_arbitration_callback()` | 36 行 | DiskArbitration 即时插拔检测框架 | 零 |

`diskutil info` 解析逻辑在 `_find_ntfs_volumes`（volume_monitor.py）中也有一份重复实现。日后修改解析逻辑时容易遗漏。

**后果**：增加维护负担，修改 `diskutil info` 解析需保持三处同步（`_find_ntfs_volumes`、`get_volume_info`、`check_windows_hibernation`）。

---

## 📊 汇总

| 严重度 | # | 问题 | 确定性 |
|--------|---|------|--------|
| 🔴 致命 | 1 | `_scan` 死锁（threading.Lock 不重入） | CONFIRMED |
| 🟠 高风险 | 2 | 休眠弹窗结果未捕获 | CONFIRMED |
| 🟠 高风险 | 3 | 后台线程操作 AppKit GUI | CONFIRMED |
| 🟠 高风险 | 4 | 恢复路径异常逃逸杀线程 | CONFIRMED |
| 🟡 中风险 | 5 | `on_change` 无异常保护 | CONFIRMED |
| 🟡 中风险 | 6 | LaunchAgent 不执行 unload/load | CONFIRMED |
| 🟡 中风险 | 7 | `size_bytes/free_bytes` 变化不触发 UI 更新 | CONFIRMED |
| 🟡 中风险 | 8 | `show_status` 定时器泄漏 | CONFIRMED |
| 🟡 中风险 | 9 | 法律声明首次启动不自动弹出 | CONFIRMED |
| 🟢 低风险 | 10 | `get_volume_info` 等死代码 | CONFIRMED |

## 建议修复顺序

1. **死锁**（#1）— 将 `threading.Lock` 改为 `threading.RLock`，或重构 `_scan` 在锁外调用回调。这是**确定性死锁**，首次插入 NTFS 卷即触发。
2. **休眠弹窗**（#2）— 捕获 `rumps.alert` 返回值，用户选"取消"则 `return`。
3. **后台线程 GUI**（#3）— 用主线程队列调度弹窗。可参考 `rumps.timers` 或 `dispatch_async`。
4. **异常传播**（#4 + #5）— 为 `_do_mount`/`_do_eject` 加 try/except，在 `_poll_loop` 加异常防护。
5. **LaunchAgent**（#6）— 启用/禁用时调用 `launchctl load/unload`。
6. **其余中低风险**（#7-#10）— 按需修复。

## 与人工审查（code-review.md）对比

| 项目 | 人工审查 | 自动化扫描 |
|------|----------|-----------|
| locale 兼容性 | 🚫 误报（未发现已用 `-plist`） | ✅ 正确 REFUTED |
| 死锁 | ❌ 漏报 | ✅ 命中（最严重发现） |
| 线程安全 GUI | ✅ 提到 | ✅ 深入 + 调用链完整 |
| LaunchAgent 不卸载 | ❌ 漏报 | ✅ 命中 |
| `on_change` 无保护 | ❌ 漏报 | ✅ 命中 |
| 其他 | 部分覆盖 | 系统性覆盖 |
