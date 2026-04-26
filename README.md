# Yes2All

Auto-approve agent tool-call prompts in **Cursor**, **VS Code** (Copilot Chat, Claude, Codex) via the Chrome DevTools Protocol.

Connects to your editor's CDP WebSocket, finds pending approval buttons by class-name and verb matching, and dispatches real mouse events to accept them — so agentic workflows run unattended.

- [TL;DR](#tldr)
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
code --remote-debugging-port=9333

# Run in foreground
uv run yes2all watch --port 9333

# Or install as a background service (macOS / Linux)
uv run yes2all service install --port 9222 --port 9333
```

## Supported Prompts

| Editor | Prompt type | What gets clicked |
|---|---|---|
| Cursor | Tool-call buttons | Run / Allow / Approve / Accept / Yes |
| VS Code | Chat-question carousel | First affirmative option + Submit |
| VS Code | Chat-confirmation widget | Allow button |
| VS Code | Codex agent prompts | "Yes" radio + Submit (webview iframe) |
| VS Code | Claude Code prompts | Affirmative button or "Yes" radio + Submit (webview iframe) |

## CLI Reference

| Command | Description | Platform |
|---|---|---|
| `yes2all watch --port PORT [--port …] [--interval N] [--countdown N]` | Run y2a-service in foreground | All |
| `yes2all targets --port PORT` | List CDP targets on a port | All |
| `yes2all probe --port PORT [--click]` | Find (and optionally click) approval buttons | All |
| `yes2all service install --port PORT [--interval N] [--no-sweep-tabs]` | Install y2a-service (launchd / systemd) | macOS, Linux |
| `yes2all service uninstall` | Remove y2a-service | macOS, Linux |
| `yes2all service status` | Check y2a-service status | macOS, Linux |
| `yes2all menubar` | Run y2a-menubar in foreground | macOS |
| `yes2all service install-menubar` | Auto-start y2a-menubar at login | macOS |
| `yes2all service uninstall-menubar` | Remove y2a-menubar auto-start | macOS |

**y2a-menubar** is a native macOS menu-bar app built with [rumps](https://github.com/jaredks/rumps). Icon: **✓** when running, **○** when stopped. Flashes green on each approval click. Menus: Start/Stop, Watched Ports, Settings, Launch w/CDP, About.

## Logs and Config

| | macOS | Linux | Windows |
|---|---|---|---|
| Logs | `~/Library/Logs/yes2all/` | `journalctl --user -u com.yes2all.watcher` | stdout |
| Config | `~/Library/Application Support/yes2all/` | `~/.local/share/yes2all/` | `%APPDATA%/yes2all/` |

## License

Copyright 2026 Mikhail Yurasov \<<me@yurasov.me>\> — [Apache 2.0](LICENSE)
