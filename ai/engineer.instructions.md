_Rev. 5_

# Engineer Instructions - Yes2All <!-- omit in toc -->

- [Build / Run / Test](#build--run--test)
- [Service Operations](#service-operations)
- [Local-Only Folders](#local-only-folders)
- [iCloud Drive Constraints (Environment, Not Code)](#icloud-drive-constraints-environment-not-code)
- [Editor DOM Facts (Verified via Live CDP Probes)](#editor-dom-facts-verified-via-live-cdp-probes)
- [Click Handlers (finder.py)](#click-handlers-finderpy)
- [Defer-While-Typing / Focus Preservation](#defer-while-typing--focus-preservation)
- [Menu-Bar App (macOS)](#menu-bar-app-macos)
- [Gotchas](#gotchas)
- [Conventions](#conventions)

Editable, project-specific notes on how to develop this project. Rewrite freely to keep the best version
(not append-only). The commit and safety policies live in `engineer.agent.md`. Consolidated on import
(2026-08-08) from the project's pre-Solaris `ai/ai-coder.instructions.md` (full history in the source
repo's git log).

## Build / Run / Test

- install: `uv sync` (from the repo root; embedded mode - the repo root is the project root)
- run (foreground): `uv run yes2all watch --port 9222 --port 9333 --interval 1`
- debug helpers: `uv run yes2all probe` (dump candidate buttons), `uv run yes2all targets` (list CDP targets)
- lint/format: `uv run ruff format <paths>` after every edit; config in `pyproject.toml`
  (`[tool.ruff]`, line length 120, double quotes). VS Code formats on save via `.vscode/settings.json`
  (needs the `charliermarsh.ruff` extension).
- test: `PYTHONPATH="$(pwd)/src" .venv/bin/python -m pytest tests/ -q` (pytest in the dev group since
  2026-08-08). Covers plist/systemd round-trips (incl. spaced paths), JS placeholder substitutions, state
  persistence, and a `node --check` syntax sweep over every fully-prepped JS handler.
- **On an iCloud Drive checkout, `uv run yes2all` breaks** - prefix with `PYTHONPATH="$(pwd)/src"`
  (see iCloud constraints below).
- Editors under test must be launched with `--remote-debugging-port` (Cursor 9222, VS Code 9333 by
  convention); CDP endpoints `http://localhost:<port>/json` and `/json/version`. The `User-Agent` token
  (`Cursor/x.y.z` vs `Code/x.y.z`) discriminates the two.

## Service Operations

- Reload after code changes: `uv run yes2all service uninstall && uv run yes2all service install
  --port 9222 --port 9333 --interval 1` (add `--countdown <C> --resume-delay <R> [--no-sweep-tabs]` to
  match the previous install; read existing args with
  `/usr/libexec/PlistBuddy -c "Print :ProgramArguments" ~/Library/LaunchAgents/com.yes2all.watcher.plist`).
- All flags (`--port`, `--interval`, `--countdown`, `--resume-delay`, `--sweep-tabs`) are persisted into the
  launchd plist / systemd unit `ExecStart`; changing them requires uninstall + reinstall (or the menubar,
  which does this for you). `--countdown` is always written, even when 0.
- macOS labels: `com.yes2all.watcher` and `com.yes2all.menubar` (`LimitLoadToSessionType=Aqua`), plists in
  `~/Library/LaunchAgents/`. Logs: `~/Library/Logs/yes2all/yes2all.{out,err}.log` and
  `menubar.{out,err}.log`.
- **`RunAtLoad` does not reliably start Aqua-limited jobs** (2026-07-04): `launchctl load -w` loads but
  does not start the job when triggered programmatically (job shows PID `-`, exit 0, no process).
  `service.py`'s `_launchd_kickstart(label)` (`launchctl kickstart -k gui/<uid>/<label>`) runs at the end
  of `launchd_install` / `menubar_install` so installs and settings-change reinstalls always end with a
  running process. Manual: `launchctl kickstart -k "gui/$(id -u)/com.yes2all.watcher"`; verify with
  `launchctl print "gui/$(id -u)/<label>" | grep -E 'state|pid'`. After editing `service.py`, reinstall
  the menubar too - its running copy keeps the old code.
- Pause/resume = SIGSTOP/SIGCONT to the watcher PID (keeps the plist loaded; `KeepAlive` does not respawn a
  stopped process). `service.py` helpers: `launchd_pid()`, `launchd_is_paused()`, `launchd_pause()`,
  `launchd_resume()`. Quit resumes first so `launchctl unload`'s SIGTERM is delivered.
- The service only polls ports passed via `--port`. If a handler "doesn't fire" for VS Code, first check
  that 9333 is in the installed plist's `ProgramArguments`.
- Recommended interval >= 1.0s when `--sweep-tabs` is on (each inactive tab adds ~1.5s per cycle).
- `service.py` embeds `PYTHONPATH=<src>` into generated units via `_src_dir()` - keep this; it makes
  background jobs import reliably regardless of editable-install state.

## Local-Only Folders

Scratch that should never be tracked lives in `__`-prefixed folders (the repo's `.gitignore` already has
`__*`): `__research/`, `__history/`, `__out/`. **Durable conclusions get folded into this file or
`ai/spec.md` before a `__research/` report is considered done.**

## iCloud Drive Constraints (Environment, Not Code)

The working copy lives under iCloud Drive (path contains spaces). Two verified consequences
(details: source git log around 2026-06-07):

1. **Editable install is not importable**: uv's `_editable_impl_yes2all.pth` sorts before
   `_virtualenv.pth` and gets dropped during site init, so `uv run yes2all` /
   `import yes2all` fail with ModuleNotFoundError even after a clean `uv sync`. Bulletproof workaround:
   `PYTHONPATH="$(pwd)/src" .venv/bin/yes2all <cmd>` (or `uv run --no-sync`). Do not rely on supplementary
   `.pth` tricks - they are fragile.
2. **launchd agents cannot run from iCloud** (hard blocker): TCC denies background agents access to
   `~/Library/Mobile Documents/`; jobs exit 126 with `Operation not permitted`. `service install` /
   `install-menubar` cannot work from an iCloud checkout. Options: venv/install outside iCloud, or run
   foreground. The menubar app runs fine foreground (GUI session keeps iCloud access).
- Foreground fallback (user's chosen mode):
  `export PYTHONPATH="$(pwd)/src"; nohup .venv/bin/yes2all watch --port 9222 --port 9333 --interval 1 >
  /tmp/y2a_watch.log 2>&1 &` and `nohup .venv/bin/yes2all menubar > /tmp/y2a_menubar.log 2>&1 &`
  (does not survive reboot).

## Editor DOM Facts (Verified via Live CDP Probes)

Selector knowledge rots as editors update - re-verify against a live editor via CDP before trusting it.

- **Cursor** (3.x, Electron/Chromium): single page target at `vscode-file://.../workbench.html`; approval
  UI is in the workbench DOM (no iframes/webviews). Approval buttons:
  - Classic: `div.composer-run-button.anysphere-button` (no `role="button"`, no aria-label - match by
    class fragment) under `...composer-tool-call-status-row`.
  - Newer builds: `button.ui-button.ui-shell-tool-call__run-btn` with text like `Run⌥⌘Y` (verb +
    shortcut glyphs, no whitespace); siblings `__skip-btn` and a mode dropdown.
  - Buttons carry the *tool's* verb (`Fetch`, `Read`, ...), not just `Run` - anything matching the
    Cursor-specific classes is treated as an approval button regardless of text
    (`isApprovalSpecific()`); the strict verb whitelist is only the fallback for non-Cursor UIs.
  - Exclude `span.mcp-header-verb` (description text) and collapsed status headers like
    `Run MCP attempted` - `strictVerbMatch()` requires the first alpha run to be a verb and all
    later runs <= 1 char.
  - **Questionnaire (native user-question) UI** (verified live 2026-08-09): container classes
    `composer-questionnaire-toolbar` under a `has-pending-questionnaire` ancestor; its "Continue ⏎"
    button carries `composer-run-button` classes, so it matches `isApprovalSpecific()` and, unless
    gated, is clicked every tick (acting on a user question) while starving real approvals later in
    the DOM walk (first-match-only clicking). All Cursor page finders skip
    `[class*="composer-questionnaire"], .has-pending-questionnaire` subtrees when
    ignore-user-questions is on. Structure (probed live): options are
    `div.composer-questionnaire-toolbar-option[role=button]`; the "Other" option carries
    `-option-freeform` and pairs with `textarea.composer-questionnaire-toolbar-freeform-input`;
    actions are Skip/Continue divs; a `-stepper-label` shows "N of M" for multi-question forms. With
    ignore-user-questions OFF, `CLICK_QUESTIONNAIRE_JS` answers each question: select freeform, set the
    textarea via the native value setter + input event (React ignores plain .value writes), click
    Continue, and mark `data-y2a-q-done=<stepper>` so it waits for the stepper to advance.
  - Chat input: `div.aislash-editor-input[contenteditable]` (ancestor `composer-input-blur-wrapper`).
  - Inactive chat tabs are **unmounted**; sweep mode activates a tab with a real `mousedown` (click alone
    is ignored), waits for `.active` + composer text change, then restores the original tab.
- **VS Code Copilot Chat** (main-page DOM, CDP-drivable):
  - Question carousel: `div.chat-question-carousel-container` > `div.chat-question-list[role=listbox]` >
    `div.chat-question-list-item[role=option]` (`aria-label="Option N: <label>"`); submit anchor
    `a.monaco-button.chat-question-submit` (siblings `-close` / `-collapse-toggle` are NOT submit).
  - Confirmation widget: `div.chat-confirmation-widget-container` with
    `a.monaco-button.monaco-text-button` "Allow" / `.secondary` "Skip" (Allow often inside a
    `.monaco-button-dropdown` split-button - exclude `.secondary` and chevrons).
  - Plain-text yes/no questions: last `.chat-markdown-part` ends with `?` and matches `CONFIRM_RE`;
    answer typed via CDP `Input.insertText` + Enter, scoped to the same chat widget.
- **Codex (OpenAI) extension**: approval UI in a nested `#active-frame` iframe inside a webview - handler
  runs on **iframe** CDP targets. Two UI generations: (1) radios `button[role=radio][type=submit]` with
  aria-label starting "Yes" + a "Submit" button; (2) the 2026 "request card" (verified live in Cursor
  2026-08-08): plain buttons where the affirmative is "Allow once ⏎" -
  `type=submit` in the plain card but **`type=button` in the split-button (dropdown) variant** -
  "Deny\nEscape" is a regular button, and a collapsible header button starts with "Run ..." - so match
  by the SUBMIT_POSITIVE verb set (which deliberately has no "run") across all buttons, submit-type
  first, AND require a negative-labeled sibling button (Deny/Decline) within 3 ancestor levels: the
  composer's standalone "Approve for me" approval-mode selector also starts with "Approve" and clicking
  it toggles that menu every tick (bogus-blink bug, fixed 2026-08-08 v1.5.2). Claude webview prompts are handled the same
  way (iframe targets).
- **One webview != one CDP target** (verified live 2026-08-08): the Claude Code panel surfaces as ~4
  iframe targets sharing the same `vscode-webview://` origin, and the user's caret and a pending prompt
  can sit in *different* frame documents. Any per-frame focus/typing logic must therefore aggregate
  across all webview frames on the port (see `IFRAME_TYPING_PROBE_JS` + the cli-side skip); a guard
  inside a single handler is not enough. `document.hasFocus()` is required before trusting
  `activeElement` - it lingers after focus leaves a doc.

## Click Handlers (finder.py)

- Per tick, per port, the service evaluates on each page target: the Cursor finder (or sweep variant),
  `CLICK_CHAT_QUESTION_JS`, `CLICK_CHAT_CONFIRMATION_JS`, `DETECT_CHAT_TEXT_CONFIRM_JS`; plus
  `vscode-webview://` iframe targets (others skipped): `CLICK_CODEX_PROMPT_JS`, `CLICK_CLAUDE_PROMPT_JS`
  (one CDP session per webview, both handlers on it).
- **Clicks must be full synthetic sequences**: `pointerdown -> mousedown -> pointerup -> mouseup -> click`
  with `composed:true`, coords, `buttons`, `pointerType:'mouse'`. Cursor 3.3+ ignores `.click()` and
  MouseEvent-only triplets (React listens for PointerEvent first). Since 2026-08-08 there is ONE canonical
  click (`__y2aRealClick` in `_JS_REAL_CLICK_FN`), injected into every handler via `__Y2A_*__` lib tokens
  expanded at import (`_expand_lib`); the typing-guard and focus-restore helpers are shared the same way.
  Import-time asserts fail loudly if a token is unexpanded or a handler ships a non-pointer realClick -
  never hand-copy a click implementation again.
- CDP evaluates carry timeouts (`cdp.DEFAULT_TIMEOUT` 15s; sweep gets 60s) so a suspended renderer can't
  freeze the watch loop. Port-unreachable logs only fire on down/up transitions.
- `--answer-text-questions/--no-answer-text-questions` (default on, plumbed through service/plist/menubar
  config) controls the plain-text "shall I proceed?" auto-Yes; that handler now also honors the
  defer-while-typing guard (it used to steal focus mid-typing).
- Positive verbs: `yes|allow|approve|accept|run|continue|confirm|ok`; negative:
  `no|stop|cancel|deny|reject|skip`. Carousel falls back to the first non-negative option when no
  positive matches. `data-y2a-*` attributes prevent re-answering.
- Countdown badge (`COUNTDOWN_BADGE_JS`) shows before clicking (default 3s; 0 = instant, no badge).
- "Ignore user questions" (on by default) skips prompts that are questions to the human (e.g. Claude
  Code's AskUserQuestion picker / carousels with no Yes-like option).

## Defer-While-Typing / Focus Preservation

- Synthetic clicks displace in-page focus (the editor re-focuses the chat that owned the clicked button).
  Focus-restore from a saved element does not survive Cursor's tab unmount/remount - the real fix is
  **defer-while-typing**, and since 1.3.0 it is **keystroke-recency-based**: a capture-phase keydown hook
  stamps `data-y2a-last-key` per document, and `shouldDeferForTyping()` holds while the caret is in a
  chat input (page handlers: known chat-input containers; webview handlers: any input, focus-chain via
  `hasFocus()` + `#active-frame`) AND the last keystroke is younger than `--resume-delay` (default 3s,
  0 disables). Approvals resume that long after the last keystroke - there is no separate cap
  (`--max-defer` was removed in 1.3.0; the flag is still accepted hidden as a no-op for old units).
- Webview (Claude/Codex) prompts: the watcher probes ALL webview frames per port
  (`IFRAME_TYPING_PROBE_JS`) and skips every webview handler while any frame - or any page handler -
  reports typing (see the multi-frame webview note above). `with_resume_delay(js, secs)` in `finder.py`
  substitutes the placeholder; call sites in `cli.py`.

## Menu-Bar App (macOS)

- `menubar.py` (rumps): run foreground `uv run yes2all menubar`; auto-start via
  `service install-menubar` / `uninstall-menubar`.
- Hides the Dock icon via `setActivationPolicy_(1)` (NSApplicationActivationPolicyAccessory).
- Config persistence: menubar settings (ports, interval, sweep, countdown, resume-delay, launch apps) go to
  `config.json` in the platform data dir via `state.write_config()`; on startup it hydrates from
  `config.json`, then overrides from the installed plist (`service.read_installed_args()`).
- Ports UI: `KNOWN_PORTS` = 9222 Cursor, 9333 VS Code; labels live-detected via `/json/version`;
  refuses to uncheck the last port. Rebuild the submenu with `_rebuild_ports_submenu()` - rumps
  `insert_before(separator, ...)` does not work, and rumps swallows callback exceptions silently
  (check `menubar.err.log`).
- Toggle is three-state Start / Pause / Resume (SIGSTOP model above). Icons: flat theme-aware checkmark
  (`icon-{off-,}{dark,light}[@2x].png`), picked by `_menu_icon(loaded)` + `_system_is_dark()`; About
  dialog uses the 256px variants. Regenerate with `uv run --with pillow python scripts/render_icon.py`.
- Data dir (`state._data_dir()`): `~/Library/Application Support/yes2all/` (macOS),
  `$XDG_DATA_HOME/yes2all/` (Linux), `%APPDATA%/yes2all/` (Windows).

## Gotchas

- rumps swallows callback `KeyError`s/exceptions and logs them to `menubar.err.log` - bugs are silent in
  the UI; always tail the err log when a menu item "does nothing".
- The wheel force-includes `src/yes2all/assets` (hatch `force-include`); the resulting assets-only
  `site-packages/yes2all/` dir can shadow the package as a namespace package on broken editable installs.
- Platform matrix: core `watch`/`probe`/`targets` cross-platform; `service` macOS+Linux; menubar
  macOS-only (platform guard on the CLI command); `install-win.bat` runs foreground.

## Conventions

- Default working style: terse responses; tables when comparing options; lead with an
  explicit recommendation; give the bare command first, then variants.
- **On releasing a new version, relaunch the running service** so it picks up the released code
  (launchctl `kickstart -k gui/<uid>/com.yes2all.watcher` and `.../com.yes2all.menubar`), then verify the
  new "watching ports ..." start line in the out log (user direction 2026-08-08).
- **Every release also gets deployed to the second machine** (user direction 2026-08-08): the host,
  checkout path, and rsync-based recipe (its git is unusable) live in `ai/.memory/resources.md`. Deploy,
  reinstall the service preserving that machine's installed plist settings, and verify its out-log start
  line shows the new version's flags. Do this in the same turn as the release, without being asked.
- Broad project reviews are defect hunts: prioritize concrete bugs, regressions, cross-platform failures,
  and missing tests; support findings with diagnostics or focused runtime evidence (2026-07-25).
- Selector/DOM claims must be verified against a live editor via CDP probe before being recorded here.
