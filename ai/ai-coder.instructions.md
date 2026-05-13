# AI Coder Instructions

Project-specific directions captured from the user. Update this file whenever the user provides new implementation-relevant information (setup, debugging, testing, preferences).

## Platform support

- Core functionality (`watch`, `probe`, `targets`) is cross-platform (macOS, Linux, Windows).
- `service install/uninstall/status` works on macOS (launchd) and Linux (systemd). Windows users run `watch` manually or use Task Scheduler.
- y2a-menubar is macOS-only (`rumps` + AppKit). The `menubar` CLI command has a platform guard.
- `state.py` uses `_data_dir()` for platform-appropriate paths: `~/Library/Application Support/yes2all/` (macOS), `$XDG_DATA_HOME/yes2all/` (Linux), `%APPDATA%/yes2all/` (Windows).
- `install-macos.sh` is macOS-only (bash + launchctl). `install-linux.sh` is the Linux equivalent (bash + systemd). `install-win.bat` is the Windows equivalent (runs y2a-service foreground, targets, probe).

## Development Environment

- **Cursor** is currently running locally with `--remote-debugging-port=9222`.
  - CDP endpoint: `http://localhost:9222/json` (target list), `http://localhost:9222/json/version` (browser info).
  - Use this live instance for development and discovery of approval-button selectors.

## Editor DOM facts (verified via live CDP probe)

- Cursor 3.1.17 (Electron 39, Chrome 142). Single page target at `vscode-file://.../workbench.html`. No iframes, no `<webview>` elements — approval UI lives directly in the workbench DOM.
- Cursor's agent tool-call approval **Run** button:
  - Container: `div.composer-run-button.anysphere-button` (also has tailwind utility classes: `flex flex-nowrap items-center justify-center gap-[4px] px-[6px] rounded cursor-pointer ...`)
  - Visible label: nested `<span class="truncate">Run</span>` inside `span.inline-flex.items-baseline...`
  - Lives under `div.composer-tool-call-content > div.composer-tool-call-control-row > div.composer-tool-call-status-row`
  - No `role="button"`, no `aria-label`, not a `<button>` — must match by class fragment.
- The MCP tool-call header also contains a `<span class="mcp-header-verb">Run</span>` (the word "Run" in the description text). It must be **excluded** — the finder does this by requiring a clickable ancestor, since `mcp-header-verb` has no clickable ancestor matching our class fragments.

## Approval-button verbs to match

`Run`, `Allow`, `Approve`, `Accept`, `Yes`. Cursor also shows a "Use Allowlist" dropdown next to Run (caret) — out of scope for the auto-click path.


## Cross-tab approvals (verified)

- Cursor renders each chat as a VS Code editor tab (`div.tab[role="tab"]` with descendant `.composer-tab-label`). **Inactive chat tabs are NOT mounted in the DOM** — their composer body is unmounted until the tab is focused.
- To activate a tab, `tab.click()` is insufficient — the workbench listens for **mousedown** on tabs. Dispatch a real `MouseEvent("mousedown")` (then mouseup/click) at the tab's center to switch.
- Detect that the new chat actually re-rendered by snapshotting `.composer-bar` innerText before activation and waiting until the tab is `.active` AND the composer text changes (poll up to ~1.2s, then 150ms settle).
- After scanning each non-active tab, restore the originally-active tab so the user isn't disrupted.
- The `watch` CLI defaults to `--no-sweep-tabs` (active-tab-only); `--sweep-tabs` enables cycling through inactive Cursor chat tabs.
- Default countdown is 3 seconds (badge shown before clicking).

## Daemon

- macOS launchd label `com.yes2all.watcher`, plist at `~/Library/LaunchAgents/`. Logs at `~/Library/Logs/yes2all/yes2all.{out,err}.log`.
- Reload after code changes: `uv run yes2all service uninstall && uv run yes2all service install --port 9222 --port 9333 --interval 1`.
- Recommended interval ≥1.0s when sweep is on (each inactive tab adds ~1.5s to a poll cycle).

## Service install flags

- `uv run yes2all service install --port 9222 --port 9333 --interval 1` — default; sweeps inactive tabs.
- `uv run yes2all service install --port 9222--port 9333 --interval 1 --no-sweep-tabs` — foreground tab only (no tab switching).
- `--sweep-tabs/--no-sweep-tabs` is persisted into the launchd plist / systemd unit's `ExecStart`. To change mode, `service uninstall` then reinstall.

## New approval button variant (Cursor newer builds)

- `<button class="ui-button ui-shell-tool-call__run-btn">` with text `Run⌥⌘Y` (verb + keyboard shortcut glyphs concatenated, no whitespace).
- Sibling: `<button class="ui-button ui-shell-tool-call__skip-btn">Skip</button>` and a `ui-shell-tool-call__mode-dropdown-trigger` ("Ask Every Time").
- Finder updates: added `ui-button` and `ui-shell-tool-call__run-btn` to `CLICKABLE_CLASS_FRAGMENTS`; matching now uses `firstWord(text)` (first run of `[A-Za-z]+`) so verbs are matched even when shortcut glyphs are appended; capped match text length at 40 chars to avoid matching long messages.

## macOS menu-bar app

- Module: `src/yes2all/menubar.py` using `rumps` (added to deps as macOS-only). Run foreground with `uv run yes2all menubar`.
- LaunchAgent label `com.yes2all.menubar`, plist at `~/Library/LaunchAgents/`. `LimitLoadToSessionType=Aqua` so it only runs in the GUI session.
- Install/remove auto-start: `uv run yes2all service install-menubar` / `uninstall-menubar`. Logs at `~/Library/Logs/yes2all/menubar.{out,err}.log`.
- Title icon: `✓` service loaded, `○` not loaded. Polls `launchctl list` every 3s.
- Menu: Start / Stop / Cycle Cursor tabs (toggle, reinstalls service) / Open log / Quit.

## Hide Python from Dock

- `menubar.py` calls `NSApplication.sharedApplication().setActivationPolicy_(1)` (NSApplicationActivationPolicyAccessory) before constructing the rumps App. This is the programmatic equivalent of `LSUIElement=1` and removes the Python rocket from the Dock.

## VS Code Copilot Chat carousel prompts

- VS Code's Copilot Chat tool-confirmation prompt is a "chat-question carousel": `div.chat-question-carousel-container` (role=`region`, aria-label `Chat question: ...`) in the main page DOM (NOT inside a webview, so CDP can drive it).
- Inside it: `div.chat-question-list` (role=`listbox`, aria-label `confirm`) containing `div.chat-question-list-item[role="option"]` elements with `aria-label="Option N: <label>"`. Affirmative is typically option #1 (e.g. "Yes, run it"); negative is e.g. "Stop". Footer hint: `⌘↵ to submit`.
- Submit anchor: `a.monaco-button.chat-question-submit` (sibling anchors `chat-question-close` and `chat-question-collapse-toggle` are NOT submit — exclude them).
- Handler: `CLICK_CHAT_QUESTION_JS` in `finder.py`. Picks the first option matching `^(yes|allow|approve|accept|run|continue|confirm|ok)\b` (skipping any matching `^(no|stop|cancel|deny|reject|skip)\b`), real-event-clicks the option to select it, then real-event-clicks the submit button (fallback: dispatches Cmd+Enter on the listbox).
- The service runs both the Cursor finder AND `CLICK_CHAT_QUESTION_JS` per page each tick. Verified live on port 9333 with a real "Run touch ~/tmp.file?" prompt.

## VS Code Copilot Chat confirmation widget (Allow / Skip)

- Second VS Code prompt variant: `div.chat-confirmation-widget-container` (aria-label `Chat Confirmation Dialog ...`). Inner button row: `div.chat-confirmation-widget-buttons` containing `a.monaco-button.monaco-text-button` "Allow" (aria-label `Allow (⌘Enter)`, often inside a `.monaco-button-dropdown` split-button) and `a.monaco-button.secondary.monaco-text-button` "Skip" (aria-label `Proceed without executing this command (⌥⌘Enter)`).
- Handler: `CLICK_CHAT_CONFIRMATION_JS`. Iterates each widget, picks first non-`secondary`, non-`monaco-dropdown-button` `monaco-button` whose label matches the positive regex; never clicks anything matching the negative regex. Real-event-clicks (mousedown/mouseup/click).
- The original Cursor finder also matches "Allow" (because `monaco-button` is in `CLICKABLE_CLASS_FRAGMENTS` and "Allow" is in `VERBS`) but the dedicated handler is safer because it explicitly excludes `.secondary` and split-button chevrons.
- Service loop now evaluates three handlers per page per tick: cursor finder (or sweep), `CLICK_CHAT_QUESTION_JS`, `CLICK_CHAT_CONFIRMATION_JS`.

## Multi-port service

- `yes2all watch --port 9222 --port 9333 ...` polls multiple CDP endpoints in a single process, looping ports each tick.
- `yes2all service install --port 9222 --port 9333` writes both `--port` args into the launchd plist `ProgramArguments` array (and into systemd `ExecStart`).
- Internal API change: `service.install(ports: list[int], interval, sweep_tabs)`, `launchd_plist(ports, ...)`, `systemd_unit(ports, ...)`. Menubar app defaults to `[9222, 9333]`.
- Per-tick log lines now include the port: `CLICKED on '9333/Welcome' ...`.

## Menubar config persistence

- `service.read_installed_args()` parses the installed launchd plist's `ProgramArguments` and returns `{ports, interval, sweep_tabs}` (or `None`).
- The menubar app hydrates from this on startup and on every status tick, so CLI-driven `service install --port ...` changes are preserved across menubar reinstalls (e.g., toggling "Cycle Cursor tabs").

## Menubar port checkboxes

- Menubar exposes a "Ports" submenu with a checkbox per known port (`PORT_CHOICES`: Cursor 9222, VS Code 9333).
- Toggling a checkbox updates `self.ports` and, if the service is loaded, reinstalls the LaunchAgent with the new port list.
- Refuses to uncheck the last enabled port.
- Checkbox state is also re-synced from the plist on every status tick.

## Menubar config persistence

- Settings changed via the menubar (ports, interval, sweep_tabs, countdown, apps) are saved to the platform data dir (`state._data_dir() / config.json`) via `state.write_config()`. On macOS: `~/Library/Application Support/yes2all/`, on Linux: `$XDG_DATA_HOME/yes2all/`, on Windows: `%APPDATA%/yes2all/`.
- On startup, the menubar hydrates from `config.json` first, then overrides from the installed plist if the service is running.
- This means settings survive even when the service is stopped — no more "install then uninstall" hack to persist port changes.
- `state.py` exports `read_config()` and `write_config()` alongside the existing `read_counts()`/`write_counts()`.

## y2a-menubar launchers

- "Launch" submenu with configurable entries: each has `name` (display), `app` (macOS app name for `open -a`), `port` (debug port).
- Default entries: Cursor (:9222), VS Code (:9333). Stored in config.json under `apps` key.
- Launches via `open -a <app> --args --remote-debugging-port=<port>`.
- "Add App…" and "Edit Apps…" menu items for adding/editing entries. Edit shows a multi-line text area with one `name, app, port` per line.

## y2a-menubar auto-detection

- Menubar labels for ports are now live-detected via `GET http://127.0.0.1:<port>/json/version`.

## Code formatting

- **Ruff** is the project formatter/linter (dev dependency).
- VS Code is configured to format on save via `.vscode/settings.json` (requires the `charliermarsh.ruff` extension).
- After making code edits, always run `uv run ruff format <changed files or dirs>` to ensure formatting is applied.
- Config lives in `pyproject.toml` under `[tool.ruff]` / `[tool.ruff.format]`.
- Both Cursor and VS Code report `Browser: "Chrome/..."` — the discriminator is the `User-Agent` token (`Cursor/x.y.z` or `Code/x.y.z`).
- Label format: `"Cursor (9222)"` when running, `"Cursor (offline)" (9222)` when port is closed. Refreshed on every status tick (3s).

## y2a-menubar icon

- Custom checkmark template icon at `src/yes2all/assets/icon.png` (22px, 44px @2x) and `icon-large.png` (128px for the About dialog).
- Generated via `uv run --with pillow python ...` (one-off; Pillow is not a runtime dep).
- Wired into `rumps.App(icon=ICON_PATH, template=True, title="")` so macOS recolors it for light/dark menu bars.
- `pyproject.toml` adds a hatch `force-include` rule to ship the assets directory in the wheel.

## Menubar icon revision

- Menubar title is back to plain text glyphs (`✓` / `○`) — no PNG icon next to it.
- About dialog uses a theme-aware large icon: `icon-large-dark.png` (black) on light system theme, `icon-large-light.png` (white) on dark system theme. Detection via `defaults read -g AppleInterfaceStyle`.

## Text-based chat confirmation questions

- VS Code Copilot Chat sometimes asks yes/no questions in plain text (e.g. "shall I proceed?", "yes or no: do X?") instead of rendering a button/widget. The agent waits for the user to type a reply.
- Handler: `DETECT_CHAT_TEXT_CONFIRM_JS` in `finder.py` detects these, `_handle_text_confirm()` in `cli.py` types "Yes" + Enter via CDP `Input.insertText` / `Input.dispatchKeyEvent`.
- Detection criteria: last `.chat-markdown-part` ends with `?`, matches `CONFIRM_RE` (shall I, should I, do you want, yes or no, proceed, etc.), chat input is empty.
- The JS scopes question + editor to the **same chat widget** (`.interactive-session` or fallback) to avoid typing into the wrong chat panel.
- When countdown > 0, a badge is shown on the question text. When countdown = 0, fires immediately with no badge. After firing, the JS focuses the chat editor, returns `shouldType: true`, and Python types "Yes" + presses Enter.
- `data-y2a-text-answered` attribute prevents re-answering the same question.
- `CDPSession.type_text(text)` and `CDPSession.press_enter()` helpers added to `cdp.py`.

## User workflow note (2026-04-25)

- When asked how to start with the macOS menu bar, provide: `uv sync` then `uv run yes2all menubar` (foreground). For auto-start at login: `uv run yes2all service install-menubar`.

## Icon design v2 (Y2A + checkmark)

- Stylized "Y2A" wordmark inside a rounded square, with a bold checkmark swoosh framing the wordmark from below (left tail dips beneath, right tail rises through the right side).
- Renderer lives at `scripts/render_icon.py`; rerun with `uv run --with pillow python scripts/render_icon.py` after tweaks.
- Same outputs as before: `icon.png`, `icon@2x.png`, `icon-large.png`, `icon-large-dark.png`, `icon-large-light.png`.

## Icon design v3 (modern Apple)

- Large/About icon: continuous-curvature squircle (superellipse n≈5) with a system-blue→indigo gradient, soft top sheen, soft drop shadow, white SF Symbols-style checkmark, and a subtle `Y2A` wordmark on the baseline.
- Menubar icon: hairline rounded square enclosing a single-weight checkmark — black-on-transparent template so macOS tints it for light/dark menu bars.
- Renderer at `scripts/render_icon.py`; rerun after tweaks.
- Color squircle works on both system themes; About dialog no longer branches on Dark Mode.

## Icon design v4 (check / y hybrid)

- Removed `Y2A` wordmark from large icon.
- Glyph is a checkmark whose long right stroke has an additional descender, so the shape reads as both a `✓` and a lowercase `y` (V vertex shared, tail drops down past the elbow).
- Same renderer at `scripts/render_icon.py`.

## Icon design v5 (flat checkmark, theme-aware)

- All previous icons removed. Single SF-style checkmark glyph, no frame, no gradient, no wordmark.
- Two color variants: `icon-dark.png` (black, for Light theme) and `icon-light.png` (white, for Dark theme), with @2x and 256px About-dialog versions.
- Menubar picks the variant via `_system_is_dark()`; loaded/unloaded state is no longer shown in the title (Start/Stop menu items reflect it).

## Icon design v6 (smaller menubar + stopped circle)

- Menubar glyph shrunk via internal padding (`MENU_PAD=0.18`) so it doesn't crowd the menu bar.
- Stopped/unloaded state shows a hairline open circle instead of the checkmark; new assets `icon-off-{dark,light}{,@2x}.png`.
- `menubar._menu_icon(loaded)` picks the right of four icons based on `(loaded, system_is_dark)`.

## Service port gotcha

- The service only polls ports passed via `--port`. If a click handler "doesn't fire" for VS Code, first verify `9333` is in the installed launchd plist's `ProgramArguments` (or in the menubar's "Ports" submenu). Default install command: `uv run yes2all service install --port 9222 --port 9333 --interval 1`.

## Known ports

- `KNOWN_PORTS` in `menubar.py`: `(9222, "Cursor")`, `(9333, "VS Code")`.
- Default ports fallback (no plist): `[9222, 9333]`.

## Carousel auto-pick fallback

- `CLICK_CHAT_QUESTION_JS` first tries to match a positive verb (`yes|allow|approve|accept|run|continue|confirm|ok`); if none of the options match, it falls back to the first non-negative option (so generic carousels like `Single confirmation, then run all 1000` / `Per-run confirmation dialog` auto-submit option #1).

## Codex (OpenAI) agent prompts

- VS Code Codex extension (`openai.chatgpt`) renders its approval UI inside a webview iframe, not in the main page DOM.
- The prompt is inside a nested `#active-frame` iframe within the webview. Radio options are `button[role="radio"][type="submit"]` with `aria-label` like "Yes", "Yes, and don't ask again for commands that start with …". A separate "Submit ⏎" button confirms, and a "Skip" button declines.
- Handler: `CLICK_CODEX_PROMPT_JS` in `finder.py`. Runs on **iframe** CDP targets (not page targets). Selects the first radio whose `aria-label` starts with "Yes", then clicks Submit.
- Service loop now also iterates `list_targets()` for iframe-type targets on each port per tick and evaluates `CLICK_CODEX_PROMPT_JS` on each.

## Class-based approval-button match for arbitrary verbs (fixed 2026-04-26)

- Cursor's MCP / shell tool-call approval button uses the *tool's* verb in its label — not just `Run`. Examples seen: `Fetch ⏎` (HTTP fetch), and presumably `Read`, `Edit`, `Search`, etc. The verb whitelist (`Run`, `Allow`, `Approve`, `Accept`, `Yes`, `Submit`) was too narrow.
- Fix: any element matching the Cursor-specific approval classes `composer-run-button` or `ui-shell-tool-call__run-btn` is treated as an approval button regardless of inner text. New helper `isApprovalSpecific(el)` short-circuits the verb check. Strict verb match still applies as fallback for non-Cursor UIs (Allow / Yes / Submit on Copilot widgets etc.).
- Applied in `FIND_APPROVAL_BUTTONS_JS`, `COUNTDOWN_BADGE_JS`, and `SWEEP_TABS_AND_CLICK_JS`. Also added the missing `ui-button` and `ui-shell-tool-call__run-btn` to `CLICKABLE_FRAGS` in the sweep variant (was lagging behind the main finder).

## Verb-match tightening: `Run MCP attempted` false positive (fixed 2026-04-26)

- Cursor renders a collapsible status header `<div role="button">Run MCP attempted</div>` after a previously-approved MCP tool call completes. The old `firstWord("Run MCP attempted") === "Run"` check matched it as an approval button, so the watcher would hammer those headers and ignore the actual `composer-run-button` Run button next to the new pending MCP approval.
- Fix: replaced `firstWord` + `txt.length > 40` gate with a stricter `strictVerbMatch(txt)`: collect all `[A-Za-z]+` runs in the visible text; the first run must be in `VERBS`, and any subsequent runs must be ≤ 1 char (so single-letter shortcut keys like the `Y` in `Run⌥⌘Y` are still allowed). This rejects multi-word phrases like `Run MCP attempted`, `Run command in terminal?`, etc.
- Applied in both `FIND_APPROVAL_BUTTONS_JS` and `COUNTDOWN_BADGE_JS` (Cursor-style section).

## Focus preservation across synthetic clicks (2026-05-09)

- Symptom: when an approval is clicked in chat A, the user's caret was getting yanked out of whatever chat input they were typing in (could be a different Cursor chat tab, a VS Code chat, etc., all in the **same** editor window). Cause: Cursor/VS Code's React handlers re-focus the chat that owned the just-clicked button after the click fires, which displaces `document.activeElement`. CDP synthetic events do **not** steal OS-level focus across apps — this is purely an in-page focus shift.
- First attempt (insufficient on its own): each same-page click handler (`COUNTDOWN_BADGE_JS`, `CLICK_CHAT_QUESTION_JS`, `CLICK_CHAT_CONFIRMATION_JS`, `SWEEP_TABS_AND_CLICK_JS`) now snapshots `document.activeElement` + selection range at the top of its IIFE and schedules `setTimeout(__y2aRestoreFocus, 0)` + an 80–120 ms backup after each `realClick`. Capture is once per script invocation (closure-scoped) so multi-click flows still reference the *original* user focus. Skips restore when the saved element is `body`/`documentElement` or has been disconnected (`isConnected`).
- Failure mode that motivated the second fix: in cross-tab Cursor scenarios (typing in chat A, approval pending in inactive chat B), sweep mode is the only way to click B. But activating B unmounts chat A's React tree, so the saved `__y2aOrigActive` becomes a disconnected node and `.focus()` is a no-op. Refocus from a stale reference cannot survive Cursor's tab unmount/remount lifecycle.
- Real fix — **defer-while-typing**: each same-page handler now also has a `userIsTyping()` helper. It returns true when `document.activeElement` is an `<input>` / `<textarea>` / `[contenteditable]` inside a known chat-input container (`.composer-bar`, `.chat-editor-container`, `.interactive-session`, `.chat-widget`, `[class*='chat-editor']`, `[class*='composer-input']`).
  - `SWEEP_TABS_AND_CLICK_JS` / `CLICK_CHAT_QUESTION_JS` / `CLICK_CHAT_CONFIRMATION_JS`: bail out at the top when typing — return `{deferred: "user-typing"}` immediately (no tab activation, no clicks).
  - `COUNTDOWN_BADGE_JS`: when `remaining <= 0`, if typing, keep the badge at "0" and leave `BADGE_ATTR` in place (no countdown reset). Click fires the moment the user pauses — within one watcher interval (~1s).
- Approvals fire as soon as the user pauses or clicks elsewhere; the deadline is preserved so the countdown doesn't visibly reset.
- Iframe-hosted handlers (Codex `CLICK_CODEX_PROMPT_JS`, Claude `CLICK_CLAUDE_PROMPT_JS` / `COUNTDOWN_CLAUDE_BADGE_JS`) are **not** patched — those run inside webview iframes whose `document.activeElement` is not the user's outer-page chat input, so neither the focus-restore nor the `userIsTyping` heuristic would see the real input. Revisit if focus-loss reports come in for those.
- Reload required after edits: `uv run yes2all service uninstall && uv run yes2all service install --port 9222 --port 9333 --interval 1` (or use the menubar Stop/Start).

## Cursor's actual chat-input class (verified via CDP probe 2026-05-10)

- The focused chat-input in Cursor is `<div class="aislash-editor-input" contenteditable="true" role="textbox">`. Its ancestor classes (in order from closest): `aislash-editor-grid` → `monaco-scrollable-element  mac` → `scrollable-div-container smooth-height` → `ai-input-full-input-box full-input-box` → `composer-input-blur-wrapper` → ...
- `[class*='composer-input']` matches `composer-input-blur-wrapper`, so the existing `userIsTyping()` heuristic worked on Cursor — **but** only handlers that actually had the heuristic. The substring also explains why VS Code's `.chat-editor-container [role='textbox']` matches.
- Added `[class*='aislash-editor']` to the heuristic for belt-and-suspenders.

## userIsTyping coverage extended to CLICK_FIRST_APPROVAL_JS (2026-05-10)

- Symptom (logs at `~/Library/Logs/yes2all/yes2all.out.log`): with `countdown=0 sweep_tabs=False interval=0.333`, the watcher logged `CLICKED on '9222/...' (active) tool='?'` ~3× per second, stealing focus every tick. This is the `CLICK_FIRST_APPROVAL_JS` path which I had not gated.
- Fix: added `userIsTyping()` + a `__DEFER_IF_TYPING` flag at the top of `FIND_APPROVAL_BUTTONS_JS`. The flag is `false` in the read-only `find` variant (so debug commands still return matches) and is rewritten to `true` via a `.replace()` in the `CLICK_FIRST_APPROVAL_JS` substitution. When typing, the click variant returns `{count: 0, buttons: [], deferred: "user-typing"}` early.
- Verified via live CDP probe on port 9222 with the user's caret in the Cursor chat input: `CLICK_FIRST_APPROVAL_JS` returned the deferred payload.
- Iframe handlers (Codex / Claude inside VS Code webviews) still unpatched — their CDP target is the iframe doc, not the outer page where the user's chat input lives. If those report focus loss, the right place to gate is in `cli.py`: query the page target for `userIsTyping` once per port per tick and skip iframe handlers for that port if true.

## Max-defer timeout for type-deferring (2026-05-10)

- New CLI flag `--max-defer N` on `yes2all watch` and `yes2all service install` (default `300`). `0` disables type-deferring (clicks fire immediately even while typing). Persisted in launchd plist / systemd unit ExecStart.
- Threaded through `service.install/launchd_install/systemd_install/launchd_plist/systemd_unit/read_installed_args` and the menubar (`max_defer` is read/written in `config.json` and passed to every `svc.install(...)` call).
- Menubar UI: `Settings ▸ Max defer while typing: <N>s…` opens a `rumps.Window` for editing. Validates non-negative; 0 disables. On apply: `_save_config()` + `_reinstall_if_loaded()`. About dialog now also shows `Max defer: <N>s`.

## Pause / Resume via SIGSTOP / SIGCONT (2026-05-10)

- The menubar's toggle item is now `Start` / `Pause` / `Resume` (three states), not `Start` / `Stop`. The previous "Stop" unloaded the LaunchAgent; "Pause" instead sends `SIGSTOP` to the watcher process so the plist stays loaded (and `KeepAlive=true` doesn't respawn it — SIGSTOP doesn't kill, it suspends).
- Helpers in `service.py`: `launchd_pid()` (parses `"PID" = N;` from `launchctl list <label>`), `launchd_is_paused()` (checks `ps -p <pid> -o state=` for leading `T`), `launchd_pause()` (`kill -STOP`), `launchd_resume()` (`kill -CONT`).
- Menubar `_refresh_status` picks the label: not-loaded → `Start`; loaded + paused → `Resume`; loaded + running → `Pause`. The menu-bar icon uses the active-state checkmark only when running (paused looks the same as unloaded — the menu label disambiguates).
- `on_quit` now resumes the watcher (if SIGSTOP'd) before calling `svc.uninstall()`, so `launchctl unload`'s SIGTERM is actually delivered. Quit still removes both LaunchAgents (watcher + menubar) and exits — to bring everything back: `uv run yes2all service install-menubar`.

## Add Port menu bug (fixed 2026-05-10)

- `on_add_port` referenced `self.menu["Ports"]` but the submenu had been renamed to `"Watched Ports"`. rumps swallows callback `KeyError`s and logs them to `~/Library/Logs/yes2all/menubar.err.log`, so the bug was silent: the port wasn't appearing in the menu (and `_save_config()` / `_reinstall_if_loaded()` never ran in that handler — the plist/config got updated through some other path, e.g. a re-add or a `_refresh_status` tick).
- Fix: new `_rebuild_ports_submenu()` clears the submenu and re-adds (checkboxes → separator → Add Port… → Reset Counters). Called from `on_add_port` after the new `port_items[prt]` entry is created. Avoids `insert_before(rumps.separator, ...)` which doesn't work — separators have no key for rumps to look up.
- JS plumbing in `finder.py`: each gated handler now calls `shouldDeferForTyping()` instead of `userIsTyping()`. The new helper:
  - Reads `__Y2A_MAX_DEFER_MS` (substituted from `__MAX_DEFER_MS__` placeholder).
  - Returns `false` immediately when `__Y2A_MAX_DEFER_MS === 0` (always click).
  - When the user has focus in a chat input, stamps `<html data-y2a-defer-start="<ms>">` on first defer; subsequent ticks compare `now - start` against the max; once exceeded, clears the attribute and returns `false` (click fires through).
  - When focus moves out of any chat input, clears the attribute so the next typing session starts a fresh timer.
- Helper `with_max_defer(js, secs)` in `finder.py` does the placeholder substitution. Call sites in `cli.py`: `js`, `js_cd`, `js_chat_question`, `js_chat_confirmation`. Iframe handlers (Codex / Claude) remain unpatched.
- Verified live via CDP: `with_max_defer(CLICK_FIRST_APPROVAL_JS, 300)` returns `{deferred:"user-typing"}` while typing; `with_max_defer(FIND_APPROVAL_BUTTONS_JS, 0)` proceeds normally.

## Countdown propagation bug (fixed)

- `service.py` used to omit `--countdown` from the launchd plist when countdown was 0 (`if countdown > 0`). Since the CLI `watch` command defaults `--countdown` to `3`, omitting it meant the watcher always used 3s regardless of the menubar setting.
- Fix: always write `--countdown <value>` to both the launchd plist and systemd unit, even when 0.

## Cursor 3.3 PointerEvent requirement (fixed 2026-05-13)

- Cursor 3.3.30 (Electron 39 / Chromium 142) finally broke the `target.click()` and MouseEvent-only paths. The `composer-run-button` (and the newer `ui-shell-tool-call__run-btn`) now sits under a React root that listens for **PointerEvent** first; bare `.click()` and even a `mousedown`+`mouseup`+`click` MouseEvent triplet are silent no-ops. Symptom: watcher logs `CLICKED` every tick on the same rect but the prompt never disappears (verified with the user's Playwright MCP "Run Browser Click" approval on port 9222).
- Two click sites had this bug:
  - `CLICK_FIRST_APPROVAL_JS` substitution (the `countdown=0` path) was `target.click(); break;`.
  - `SWEEP_TABS_AND_CLICK_JS` used `btn.click()` for both the active-tab fast path and the per-tab branch.
- Fix: dispatch the full sequence `pointerdown → mousedown → pointerup → mouseup → click` at the element's center, with `composed:true`, `view:window`, `clientX/Y` + `screenX/Y`, `buttons:1` on the down phase and `buttons:0` on the up phase, and `pointerType:'mouse'` / `pointerId:1` / `isPrimary:true` for the pointer events. The shared `_REAL_CLICK_SNIPPET` Python constant is substituted into `CLICK_FIRST_APPROVAL_JS`; `SWEEP_TABS_AND_CLICK_JS` defines a JS `realClick(el)` helper with the same sequence (and aliases `activateTab = realClick` since tabs use the same listener model).
- `COUNTDOWN_BADGE_JS`'s internal `realClick` was already mostly-correct (mousedown/mouseup/click) but is still MouseEvent-only — not touched here because the user has `countdown=0`; revisit if the countdown path stops dismissing prompts on Cursor 3.3+.
- Verification: `PointerEvent("pointerdown")` + `MouseEvent("mousedown")` ... sequence at center dismisses a live `composer-run-button` on Cursor 3.3.30 (`Recent staff meeting transcript — NV-Co-SA-MY` window). MouseEvent-only does not.
- Reload after edits: `uv run yes2all service uninstall && uv run yes2all service install --port 9222 --port 9333 --interval <N> --countdown <C> --max-defer <M> [--no-sweep-tabs]` (read existing args from `/usr/libexec/PlistBuddy -c "Print :ProgramArguments" ~/Library/LaunchAgents/com.yes2all.watcher.plist`).
