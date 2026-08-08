# Yes2All - Spec <!-- omit in toc -->

- [Goal](#goal)
- [Components](#components)
- [Constraints](#constraints)
- [Open Questions](#open-questions)

Auto-approve agent tool-call prompts in Cursor and VS Code (Copilot Chat, Claude Code, Codex) via the
Chrome DevTools Protocol.

> Current specification - the single source of truth for this project. Kept **self-sufficient**: it reads
> standalone and does not reference or depend on any other file. Updated through dialogue during planning and
> development. Reconstructed on import (2026-08-08) from the original `ai/spec.txt`, the README, and the
> shipped code; the preserved initial spec is `ai/.memory/spec-v0.md`.

## Goal

A background watcher that connects to code editors (Cursor, VS Code) launched with
`--remote-debugging-port` and auto-approves the tool-call prompts that coding agents show, so agentic
sessions run unattended. It approves tool-call prompts but skips questions the agent asks the *user*
(e.g. option pickers), and defers clicking while the user is actively typing in a chat input.

## Components

- **CLI** (`yes2all`, Typer): `watch` (the poll loop), `probe` / `targets` (debugging + selector
  discovery), `service install/uninstall/status` (background service), `menubar` (macOS UI).
- **CDP layer** (`cdp.py`): WebSocket sessions per target; JS evaluation, synthetic input
  (`Input.insertText`, key events).
- **Finder** (`finder.py`): per-UI JS handlers - Cursor approval buttons (class-based match +
  strict-verb fallback), VS Code Copilot chat-question carousels and confirmation widgets, plain-text
  yes/no questions, and iframe-hosted Codex / Claude webview prompts. Real
  pointerdown->mousedown->pointerup->mouseup->click sequences (Cursor 3.3+ requires PointerEvent).
- **Service** (`service.py`): launchd (macOS) / systemd --user (Linux) install, multi-port
  `--port` args, `--interval`, `--countdown`, `--max-defer`, `--sweep-tabs` persisted into the unit;
  pause/resume via SIGSTOP/SIGCONT; `read_installed_args()` for config round-tripping.
- **macOS menu-bar app** (`menubar.py`, rumps): start/pause/resume, watched-ports checkboxes, countdown /
  interval / max-defer settings, launch-editor entries, log tailing, click counters; theme-aware icons.
- **State** (`state.py`): platform data dir (`config.json`, counters).
- **Installers**: `install-macos.sh`, `install-linux.sh`, `install-win.bat`; `scripts/` holds the icon
  renderer and a click-verification probe.

## Constraints

- Python 3.12 (`>=3.12,<3.13`), uv-managed (`pyproject.toml` + `uv.lock`), hatchling build, Ruff
  format/lint (line length 120, double quotes).
- Cross-platform core (watch/probe/targets); background service on macOS (launchd) and Linux (systemd);
  Windows runs foreground / Task Scheduler. Menu-bar app is macOS-only.
- Must keep an agentic-friendly setup (debuggable selectors, probe tooling) so agents can develop and
  test it autonomously.
- Editor DOMs change between releases (Cursor class names, VS Code widget variants) - selector knowledge
  is maintained in `ai/engineer.instructions.md` and must be re-verified against live editors via CDP.
- Published at github.com/myurasov/Yes2All (Apache-2.0).

## Open Questions

- Focus-preservation / defer-while-typing is not implemented for iframe-hosted handlers (Codex, Claude
  webviews) - revisit if focus-loss reports come in.
- Background service cannot run from an iCloud Drive checkout (macOS TCC denies launchd agents access);
  the durable fix (venv/install outside iCloud) is still open.
