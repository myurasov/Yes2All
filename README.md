# Yes2All

Auto-approve agent tool-call prompts in **Cursor** and **VS Code** (Copilot Chat, Claude Code, Codex) via the Chrome DevTools Protocol.

Yes2All connects to your editor's CDP WebSocket and handles the approval UIs that coding agents commonly show: Cursor tool-call buttons, VS Code Copilot confirmation widgets, Codex and Claude webview prompts, and plain-text yes/no confirmation questions.

- [TL;DR](#tldr)
- [Features](#features)
- [Installation](#installation)
- [Supported Prompts](#supported-prompts)
- [CLI Reference](#cli-reference)
- [Logs and Config](#logs-and-config)
- [License](#license)

## TL;DR

**macOS:**

```sh
git clone https://github.com/myurasov/Yes2All.git && cd Yes2All
uv sync && ./install-macos.sh
```

**Linux:**

```sh
git clone https://github.com/myurasov/Yes2All.git && cd Yes2All
uv sync && ./install-linux.sh
```

**Windows:**

```cmd
git clone https://github.com/myurasov/Yes2All.git && cd Yes2All
uv sync && install-win.bat
```

## Features

- Watches one or more CDP ports at once, so Cursor and VS Code can be monitored by one process.
- Shows a countdown badge before approving prompts by default (`--countdown 3`), or clicks instantly with `--countdown 0`.
- Dispatches real mouse events for button-style prompts and uses CDP input events for text confirmations.
- Optionally cycles inactive Cursor chat tabs in instant mode (`--sweep-tabs --countdown 0`), then restores the originally active tab.
- Runs in the foreground on all platforms, or as a background service on macOS (`launchd`) and Linux (`systemd --user`).
- Includes a native macOS menu-bar app for start/stop, watched ports, countdown and interval settings, log tailing, click counters, and launching editors with CDP enabled.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Editors must be launched with `--remote-debugging-port`.

```sh
git clone https://github.com/myurasov/Yes2All.git
cd Yes2All
uv sync
```

Then use the interactive installer for your platform:

| Platform | Script | Notes |
|---|---|---|
| macOS | `./install-macos.sh` | launchd service + menu-bar app, press 0 for quick-install |
| Linux | `./install-linux.sh` | systemd user service |
| Windows | `install-win.bat` | foreground mode only |

Or run manually on any platform:

```sh
# Launch editor with a CDP port
cursor --remote-debugging-port=9222
code --remote-debugging-port=9333

# Run in foreground, watching Cursor + VS Code
uv run yes2all watch --port 9222 --port 9333 --interval 1 --countdown 3

# Or install as a background service (macOS / Linux)
uv run yes2all service install --port 9222 --port 9333 --interval 1 --no-sweep-tabs --countdown 3
```

## Supported Prompts

| Editor | Prompt type | Behavior |
|---|---|---|
| Cursor | Active tool-call buttons | Clicks `Run`, `Allow`, `Approve`, `Accept`, `Yes`, or `Submit` |
| Cursor | Inactive chat tabs | Optional `--sweep-tabs --countdown 0` scans Cursor chat tabs, clicks pending approvals, then restores the original tab |
| VS Code Copilot Chat | Chat-question carousel | Selects the first affirmative option, or the first non-negative fallback, then submits |
| VS Code Copilot Chat | Confirmation widget | Clicks the positive primary button and avoids `Skip` / secondary buttons |
| VS Code Copilot Chat | Plain-text confirmation question | Types `Yes` and presses Enter when a matching yes/no question is waiting for input |
| VS Code Codex | Webview iframe prompt | Selects the `Yes` radio option and submits |
| VS Code Claude Code | Webview iframe prompt | Handles direct numbered affirmative buttons and radio + submit variants |

By default Yes2All only checks the active Cursor chat tab. Use `--sweep-tabs --countdown 0` when you want it to briefly cycle inactive Cursor chat tabs looking for pending approvals.

## CLI Reference

| Command | Description | Platform |
|---|---|---|
| `yes2all watch --port PORT [--port PORT ...] [--interval N] [--countdown N] [--sweep-tabs/--no-sweep-tabs] [--once]` | Run y2a-service in foreground | All |
| `yes2all targets --port PORT` | List CDP targets on a port | All |
| `yes2all probe --port PORT [--click]` | Find (and optionally click) approval buttons | All |
| `yes2all service install --port PORT [--port PORT ...] [--interval N] [--countdown N] [--sweep-tabs/--no-sweep-tabs]` | Install y2a-service (launchd / systemd) | macOS, Linux |
| `yes2all service uninstall` | Remove y2a-service | macOS, Linux |
| `yes2all service status` | Check y2a-service status | macOS, Linux |
| `yes2all menubar` | Run y2a-menubar in foreground | macOS |
| `yes2all service install-menubar` | Auto-start y2a-menubar at login | macOS |
| `yes2all service uninstall-menubar` | Remove y2a-menubar auto-start | macOS |

Defaults: `--port 9222`, `--interval 1`, `--countdown 3`, and active-tab-only Cursor scanning (`--no-sweep-tabs`).

**y2a-menubar** is a native macOS menu-bar app built with [rumps](https://github.com/jaredks/rumps). Icon: **✓** when running, **○** when stopped. It flashes green on each approval click and includes Start/Stop, watched port checkboxes, Add Port, Reset counters, interval/countdown settings, Cursor tab cycling, Launch w/CDP, Tail log in Terminal, and About.

## Logs and Config

| | macOS | Linux | Windows |
|---|---|---|---|
| Logs | `~/Library/Logs/yes2all/` | `journalctl --user -u com.yes2all.watcher` | stdout |
| Config | `~/Library/Application Support/yes2all/` | `~/.local/share/yes2all/` | `%APPDATA%/yes2all/` |

Windows currently runs in foreground mode through `install-win.bat`; for background operation, use Task Scheduler manually.

## License

Copyright 2026 Mikhail Yurasov \<<me@yurasov.me>\> — [Apache 2.0](LICENSE)
