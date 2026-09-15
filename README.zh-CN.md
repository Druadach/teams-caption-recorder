# Teams 会议字幕自动录制器

> 🌐 [English](README.md)

自动将 **Microsoft Teams 会议实时字幕** 保存为带时间戳的文本转录——无需会议录制权限，也不依赖官方“转录”功能。工具随 Windows 静默启动，检测到会议自动开始录制，会议结束自动收工。

```
[17:00:54] --- 陈明 ---
[17:00:54] But why?
[17:00:54] Do you know why I don't want to have a same situation, right?
[17:00:54] Because Azon have another type of palette for Yandex, we need individual palettes.
...
[17:01:10] --- 李华 ---
[17:01:10] I don't understand what a problem really.
```

## 工作原理

新版 Teams 客户端使用原生媒体引擎（slimcore）渲染字幕，字幕文本不经过网页 DOM，也不落盘、不进 IndexedDB——所以无法从文件或内存转储中获取。但字幕**会暴露在 Windows UI 自动化（UIA）无障碍树**中（屏幕阅读器正是通过这个接口读取屏幕内容的）。本工具轮询这棵树，把看到的每一行字幕记录下来。

一个轻量守护进程注册为登录自启项：

```
登录 ──> watchdog（空闲待命，几乎零 CPU 占用）
             │  检测到 "… | Microsoft Teams" 会议窗口
             ├──> 启动录制器 -> Documents/TeamsCaptions/captions_<时间戳>.txt
             └──< 窗口关闭：录制器自动退出，watchdog 回到待命，等待下一场会议
```

字幕文本从当前实际显示字幕的 Teams 顶层窗口读取：可能是会议窗口（字幕停靠在底部），也可能是 **“在独立窗口中打开字幕”** 弹出的独立窗口（标题形如 `Captions | … | Microsoft Teams` / `辅助字幕 | …`）。两者都会按窗口句柄被跟踪，且独立字幕窗口存在时优先读取它，因此在两种模式间切换不再中断转录。

## 环境要求

- Windows 10 / 11
- 新版 Teams 客户端（基于 WebView2 的版本）
- Python 3.9+ 且在 PATH 中（`python` / `pythonw`）
- 会议中已开启实时字幕（**更多操作 > 录制和转录 > 打开实时字幕**）

## 安装

```powershell
git clone https://github.com/Druadach/teams-caption-recorder.git
cd teams-caption-recorder
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装脚本会 pip 安装 `uiautomation`、向注册表 `HKCU...\Run` 写入自启项，并立即启动 watchdog。

之后每次开会只要打开字幕，转录就会自动出现在 `Documents\TeamsCaptions\` 目录。

### 手动运行（不安装）

```powershell
pip install uiautomation
python caption_recorder.py            # 立即录制当前会议，输出路径自动生成
python caption_watchdog.py            # 或以守护模式运行
```

## 输出格式

每场会议一个文件，位于 `%USERPROFILE%\Documents\TeamsCaptions`：

```
=== session 2026-08-25 17:00:54 ===

[17:00:54] --- 陈明 ---
[17:00:54] But why?
...
[17:01:02] --- 李华 ---
[17:01:02] I don't understand what a problem really.
```

以 `(数字)` 结尾的行为说话人分隔标记；分隔符之后的各行属于该说话人，直到下一个分隔符出现。屏幕上最后两行字幕仍处于实时识别修正中，因此只有等它定稿后才会写入文件。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

移除自启项并停止正在运行的 watchdog/录制器。历史转录文件不受影响。

## 已知限制

- 只能捕获**字幕面板上显示过的内容**——如果没开字幕，或 Teams 长期最小化到托盘导致字幕未渲染，对应时段的内容就抓不到。
- 从打开字幕那一刻才开始记录；之前说过的话无法回溯获取。
- 说话人名称和时间戳来自字幕面板，并非官方转录。如需具有正式效力的会议纪要，建议使用 Teams 内置的**转录**功能（会后可下载 `.docx/.vtt` 文件）。

## 隐私声明

本工具读取的仅是你在自己屏幕上已经能看到的内容。请遵守所在组织的合规政策及当地法律关于会议录制/告知的规定。

## License

[MIT](LICENSE)
