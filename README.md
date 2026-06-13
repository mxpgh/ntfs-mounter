# NTFS Mounter

macOS 菜单栏工具，一键挂载 NTFS 外置盘为读写。

## 功能

- 🖥️ 菜单栏常驻，检测 NTFS 磁盘插入
- 🔓 一键将 NTFS 磁盘挂载为读写模式
- ⏏️ 安全移除磁盘
- ℹ️ 显示磁盘容量信息
- 🔄 自动检测磁盘插拔

## 系统要求

- **macOS 12+** (Intel / Apple Silicon)
- **macOS 13+ (Ventura / Sonoma / Sequoia)** 需要安装 macFUSE + ntfs-3g（Apple 已移除原生 mount_ntfs）

## 安装

### 1. 安装依赖

macOS 13+ 用户需要安装第三方驱动：

```bash
# macFUSE（内核扩展）
brew install --cask macfuse

# ntfs-3g（通过 gromgit 维护的版本）
brew tap gromgit/homebrew-fuse && brew install ntfs-3g-mac
```

> 安装 macFUSE 后需重启电脑。

### 2. 下载 App

从 [Releases](https://github.com/mxpgh/ntfs-mounter/releases) 下载 `NTFS Mounter.app`，拖入 `/Applications`。

### 3. 使用

插入 NTFS 磁盘 → 点击菜单栏 `NTFS` 图标 → 点击 `🔓 挂载为读写` → 输入管理员密码 → 完成。

## 自行编译

```bash
pip install pyinstaller rumps pyobjc
bash build.sh
```

产物在 `dist/NTFS Mounter.app`。

## 技术栈

- Python 3.12 + [rumps](https://github.com/jaredks/rumps) (菜单栏) + pyobjc
- 挂载逻辑: `mount_ntfs -o rw,nobrowse` 或 ntfs-3g
- 打包: PyInstaller

## 免责声明

NTFS 第三方写入可能带来数据损坏风险。请勿用于存储重要数据。
