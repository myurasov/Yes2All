# Yes2All

Auto-approve agent tool-call prompts in **Cursor** and **VS Code** (Copilot Chat) via the Chrome DevTools Protocol exposed by `--remote-debugging-port`.

## Features

- **Auto-clicks** Run / Allow / Approve / Accept / Yes buttons in Cursor and VS Code Copilot Chat — so agentic workflows run unattended.
- **Multiple prompt formats** — handles Cursor's composer tool-call buttons, VS Code's chat-question carousels, and chat-confirmation (Allow/Skip) widgets.
- **Multi-port** — poll Cursor (9222) and VS Code (9333) simultaneously in a single watcher process.
- **Inactive tab sweep** — switches through Cursor chat tabs to find pending approvals in background conversations, then restores the original tab.
- **macOS menu-bar app** — checkmark icon in the menu bar with Start/Stop, port toggles, interval config, and a green flash when a click fires.
- **Background service** — installs as a macOS LaunchAgent (launchd) or Linux systemd user unit that starts on login and auto-restarts.
- **Diagnostic tools** — `targets` and `probe` commands for discovering CDP pages and approval-button selectors.

## Requirements

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- macOS or Linux
- Editor launched with `--remote-debugging-port`

## Installation

```sh
git clone https://github.com/myurasov/Yes2All.git
cd Yes2All
uv sync
```

## Quick start (macOS)

### 1. Launch your editors with debugging ports

```sh
# Cursor
/Applications/Cursor.app/Contents/MacOS/Cursor --remote-debugging-port=9222

# VS Code
code --remote-debugging-port=9333
```

### 2. Start the menu-bar app

```sh
uv run yes2all menubar
```

A ✓ icon appears in the menu bar. Click it → **Start** to begin auto-approving. Use the **Ports** submenu to enable Cursor (9222) and/or VS Code (9333).

### 3. Auto-start at login

```sh
uv run yes2all service install-menubar
```

The menu-bar app will now launch automatically on every login. Remove with `uv run yes2all service uninstall-menubar`.

## Usage

### CLI commands

| Command | Description |
|---|---|
| `yes2all targets --port PORT` | List all CDP targets on the given port |
| `yes2all probe --port PORT [--click]` | Find (and optionally click) approval buttons |
| `yes2all watch --port PORT [--port PORT2] [--interval N] [--no-sweep-tabs]` | Poll and auto-click in a loop |
| `yes2all menubar` | Launch the macOS menu-bar app (foreground) |
| `yes2all service install --port PORT [--port PORT2] [--interval N] [--no-sweep-tabs]` | Install watcher as a background service |
| `yes2all service uninstall` | Stop and remove the watcher service |
| `yes2all service status` | Check if the watcher service is loaded |
| `yes2all service install-menubar` | Auto-start the menu-bar app at login |
| `yes2all service uninstall-menubar` | Remove menu-bar auto-start |

### macOS menu-bar app

```sh
# Run once (foreground)
uv run yes2all menubar

# Auto-start at login
uv run yes2all service install-menubar
```

The menu-bar icon shows a ✓ when the watcher is loaded and ○ when stopped. It flashes green briefly whenever an approval is clicked. The menu provides:

- **Start / Stop** — toggle the background watcher
- **Ports** — enable/disable Cursor (9222) and VS Code (9333) with live status detection
- **Sweep inactive tabs** — toggle scanning of background Cursor chat tabs
- **Interval** — adjust the poll frequency
- **Open log** — view watcher output

### Background service

```sh
# Install and start (both editors, 0.5s poll, sweep on)
uv run yes2all service install --port 9222 --port 9333 --interval 0.5

# Check status
uv run yes2all service status

# Stop and remove
uv run yes2all service uninstall
```

Logs are written to `~/Library/Logs/yes2all/` on macOS.

## How it works

Yes2All connects to the editor's CDP WebSocket, evaluates JavaScript on each page target to locate approval buttons by class-name fragments and verb matching, and dispatches real mouse events (mousedown → mouseup → click) to accept them. It handles three distinct prompt types:

1. **Cursor tool-call buttons** — `div.composer-run-button` and `button.ui-shell-tool-call__run-btn`
2. **VS Code chat-question carousels** — `div.chat-question-carousel-container` with option selection + submit
3. **VS Code chat-confirmation widgets** — `div.chat-confirmation-widget-container` with Allow/Skip buttons
