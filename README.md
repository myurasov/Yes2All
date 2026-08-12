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
- Approves tool-call prompts but skips questions the agent asks *you* (on by default, `--ignore-user-questions`) — e.g. Claude Code's AskUserQuestion picker or a multiple-choice carousel with no Yes/Allow option. Disable with `--no-ignore-user-questions`.
- **Pauses while you type**: approvals are deferred while your caret is in a chat input and keys are flowing — anywhere in the editor, including inside Claude Code / Codex webview panels — and resume `--resume-delay` seconds (default 3) after your last keystroke. Typing state is re-checked ~4×/s, and the menu-bar icon dims while a pause is holding. Set `--resume-delay 0` to disable.
- Shows a countdown badge before approving prompts by default (`--countdown 3`), or clicks instantly with `--countdown 0`.
- Dispatches full synthetic pointer + mouse event sequences (required by newer Cursor builds) for button-style prompts and uses CDP input events for text confirmations.
- Auto-answers plain-text "shall I proceed?" questions with `Yes` (on by default; disable with `--no-answer-text-questions`).
- Optionally cycles inactive Cursor chat tabs in instant mode (`--sweep-tabs --countdown 0`), then restores the originally active tab.
- Runs in the foreground on all platforms, or as a background service on macOS (`launchd`) and Linux (`systemd --user`). Every CDP call carries a timeout, so a suspended editor can never wedge the watcher.
- Includes a native macOS menu-bar app for start/pause/resume, watched ports, countdown / interval / typing-delay settings, log tailing, click counters, and launching editors with CDP enabled.

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
| Cursor / VS Code Codex | Webview iframe prompt | Older UI: selects the `Yes` radio and submits. Newer "request card" UI: clicks the affirmative submit button (`Allow once`), never `Deny` or the command header |
| VS Code Claude Code | Webview iframe prompt | Handles direct numbered affirmative buttons and radio + submit variants |
| Cursor / Claude / Codex | User-facing question (no Yes/Allow option) | Left untouched for you to answer while `--ignore-user-questions` is on (the default); logged as `SKIPPED user-question` |
| Cursor | Questionnaire (native user-question form, incl. multi-select + "Other" text field) | With `--ignore-user-questions` (default): never touched, even while you select options and type. With `--no-ignore-user-questions`: selects "Other", types "I leave it to the best of your judgement, operate with best safety practices and use common sense.", and submits each question |

By default Yes2All only checks the active Cursor chat tab. Use `--sweep-tabs --countdown 0` when you want it to briefly cycle inactive Cursor chat tabs looking for pending approvals.

Yes2All tells a tool-approval apart from a user question by whether the prompt offers an affirmative option (`Yes`, `Allow`, `Approve`, `Accept`, …). Approvals always do; an open-ended question (e.g. "Which language?" → Python / TypeScript / Rust) does not, so with `--ignore-user-questions` (default) it is skipped instead of being auto-answered with an arbitrary first choice. Pass `--no-ignore-user-questions` to restore the old "pick the first non-negative option" behavior.

While you are typing in any chat input — editor-level or inside a Claude Code / Codex webview panel — all approvals on that port are held and fire `--resume-delay` seconds after your last keystroke, so a click never yanks your caret mid-thought. Deferred and resumed transitions are logged (`deferring webview approvals while typing` / `typing ended`).

## CLI Reference

| Command | Description | Platform |
|---|---|---|
| `yes2all watch --port PORT [--port PORT ...] [--interval N] [--countdown N] [--resume-delay N] [--sweep-tabs/--no-sweep-tabs] [--ignore-user-questions/--no-ignore-user-questions] [--answer-text-questions/--no-answer-text-questions] [--once]` | Run y2a-service in foreground | All |
| `yes2all targets --port PORT` | List CDP targets on a port | All |
| `yes2all probe --port PORT [--click]` | Find (and optionally click) approval buttons | All |
| `yes2all service install --port PORT [--port PORT ...] [--interval N] [--countdown N] [--resume-delay N] [--sweep-tabs/--no-sweep-tabs] [--ignore-user-questions/--no-ignore-user-questions] [--answer-text-questions/--no-answer-text-questions]` | Install y2a-service (launchd / systemd) | macOS, Linux |
| `yes2all service uninstall` | Remove y2a-service | macOS, Linux |
| `yes2all service status` | Check y2a-service status | macOS, Linux |
| `yes2all menubar` | Run y2a-menubar in foreground | macOS |
| `yes2all service install-menubar` | Auto-start y2a-menubar at login | macOS |
| `yes2all service uninstall-menubar` | Remove y2a-menubar auto-start | macOS |

Defaults: `--port 9222`, `--interval 1`, `--countdown 3`, `--resume-delay 3`, active-tab-only Cursor scanning (`--no-sweep-tabs`), user questions skipped (`--ignore-user-questions`), and text questions answered (`--answer-text-questions`).

**y2a-menubar** is a native macOS menu-bar app built with [rumps](https://github.com/jaredks/rumps). Icon: **✓** when running, **○** when stopped, dimmed **✓** while typing pauses approvals, and a green flash on each approval click. It includes Start/Pause/Resume, watched port checkboxes, Add Port, Reset counters, Interval / Countdown / Typing Delay settings, Cursor tab cycling, an "Ignore User Questions" toggle, Launch w/CDP, Tail log in Terminal, and About.

## Logs and Config

| | macOS | Linux | Windows |
|---|---|---|---|
| Logs | `~/Library/Logs/yes2all/` | `journalctl --user -u com.yes2all.watcher` | stdout |
| Config | `~/Library/Application Support/yes2all/` | `~/.local/share/yes2all/` | `%APPDATA%/yes2all/` |

Windows currently runs in foreground mode through `install-win.bat`; for background operation, use Task Scheduler manually.

## License

Copyright 2026 Mikhail Yurasov \<<me@yurasov.me>\> — [Apache 2.0](LICENSE)
