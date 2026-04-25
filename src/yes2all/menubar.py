"""macOS menu-bar app to start/stop the Yes2All background watcher.

Uses `rumps`. Run with `yes2all menubar`.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import rumps  # type: ignore[import-not-found]

# Hide the Python rocket from the Dock — run as a UI accessory (menu-bar only).
try:
    from AppKit import NSApplication  # type: ignore[import-not-found]
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory
except Exception:
    pass

from . import service as svc
from . import state as _state

_ASSETS = Path(__file__).parent / "assets"
# Two flat checkmark variants (loaded) + two open-circle variants (stopped).
# The menubar picks the pair based on system theme.
ICON_DARK = str(_ASSETS / "icon-dark.png")    # black check, for Light theme
ICON_LIGHT = str(_ASSETS / "icon-light.png")  # white check, for Dark theme
ICON_OFF_DARK = str(_ASSETS / "icon-off-dark.png")
ICON_OFF_LIGHT = str(_ASSETS / "icon-off-light.png")
ICON_FLASH = str(_ASSETS / "icon-flash.png")  # brief green pulse on click
ICON_LARGE_DARK = str(_ASSETS / "icon-large-dark.png")
ICON_LARGE_LIGHT = str(_ASSETS / "icon-large-light.png")

# Duration of the green flash after a click is observed (seconds).
FLASH_DURATION = 0.45

LOG_OUT = Path.home() / "Library" / "Logs" / "yes2all" / "yes2all.out.log"


def _menu_icon(loaded: bool) -> str:
    if _system_is_dark():
        return ICON_LIGHT if loaded else ICON_OFF_LIGHT
    return ICON_DARK if loaded else ICON_OFF_DARK


def _system_is_dark() -> bool:
    """Return True if macOS is currently in Dark Mode."""
    try:
        r = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, check=False, timeout=0.5,
        )
        return r.returncode == 0 and "Dark" in r.stdout
    except Exception:
        return False

# Known CDP ports advertised in the menu (port, default label if not running).
KNOWN_PORTS: list[tuple[int, str]] = [
    (9222, "Cursor"),
    (9333, "VS Code"),
]


def _detect_app(port: int) -> str | None:
    """Hit `/json/version` on the given CDP port and return a friendly app name.

    Returns None if nothing is listening (or response is malformed).
    Note: Electron-based apps (Cursor, VS Code) both report ``Browser: Chrome/...``;
    the only reliable discriminator is the ``User-Agent`` token (``Cursor/x.y.z``
    or ``Code/x.y.z``).
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    ua = (data.get("User-Agent") or "").strip()
    if "Cursor/" in ua:
        return "Cursor"
    if "Code/" in ua:
        return "VS Code"
    browser = (data.get("Browser") or "").strip()
    return browser.split("/")[0] if browser else None


def _is_loaded() -> bool:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
    return any(svc.LABEL in ln for ln in r.stdout.splitlines())


class Yes2AllApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Yes2All", title=None,
                         icon=_menu_icon(_is_loaded()),
                         template=False, quit_button=None)
        # Hydrate from the installed plist if present, else use defaults.
        cfg = svc.read_installed_args() or {}
        self.ports: list[int] = cfg.get("ports") or [9222, 9333]
        self.interval: float = cfg.get("interval", 0.5)
        self.sweep_tabs: bool = cfg.get("sweep_tabs", True)

        self.toggle_item = rumps.MenuItem("Start", callback=self.on_toggle)
        self.sweep_item = rumps.MenuItem("Sweep inactive tabs", callback=self.on_toggle_sweep)
        self.sweep_item.state = 1 if self.sweep_tabs else 0

        # Flash state: when the watcher reports a click, briefly swap the
        # menubar icon to a green check.
        self._flash_until: float = 0.0
        self._last_total: int = sum(_state.read_counts().values())

        # One checkbox per known port, grouped under a "Ports" submenu.
        # Label is detected live from each port's /json/version endpoint.
        self.port_items: dict[int, rumps.MenuItem] = {}
        for prt, default_name in KNOWN_PORTS:
            mi = rumps.MenuItem(self._port_label(prt, default_name),
                                callback=self._make_port_toggle(prt))
            mi.state = 1 if prt in self.ports else 0
            self.port_items[prt] = mi
        ports_menu = rumps.MenuItem("Ports")
        for mi in self.port_items.values():
            ports_menu.add(mi)
        ports_menu.add(rumps.separator)
        ports_menu.add(rumps.MenuItem("Add Port…", callback=self.on_add_port))
        ports_menu.add(rumps.MenuItem("Reset counters", callback=self.on_reset_counters))
        self.interval_item = rumps.MenuItem(
            self._interval_title(), callback=self.on_set_interval
        )

        self.menu = [
            self.toggle_item,
            None,
            ports_menu,
            self.interval_item,
            self.sweep_item,
            rumps.MenuItem("Tail log in Terminal", callback=self.on_open_log),
            None,
            rumps.MenuItem("About Yes2All", callback=self.on_about),
            rumps.MenuItem("Quit Yes2All", callback=self.on_quit),
        ]
        self._refresh_status()

    # ----- status polling ------------------------------------------------
    @rumps.timer(3)
    def _tick(self, _: object) -> None:
        self._refresh_status()

    @rumps.timer(0.25)
    def _flash_tick(self, _: object) -> None:
        total = sum(_state.read_counts().values())
        now = time.monotonic()
        if total > self._last_total:
            self._last_total = total
            self._flash_until = now + FLASH_DURATION
            self.icon = ICON_FLASH
            return
        if self._flash_until and now >= self._flash_until:
            self._flash_until = 0.0
            self.icon = _menu_icon(_is_loaded())

    def _refresh_status(self) -> None:
        loaded = _is_loaded()
        if not self._flash_until:
            self.icon = _menu_icon(loaded)
        self.toggle_item.title = "Stop" if loaded else "Start"
        # Re-hydrate from plist so CLI-driven changes (ports/interval/sweep)
        # are reflected the next time the menu reinstalls the watcher.
        cfg = svc.read_installed_args()
        if cfg:
            self.ports = cfg["ports"]
            self.interval = cfg["interval"]
            self.sweep_tabs = cfg["sweep_tabs"]
            self.sweep_item.state = 1 if self.sweep_tabs else 0
            self.interval_item.title = self._interval_title()
        # Re-detect app on each known port and refresh checkbox label/state.
        for (prt, default_name), mi in zip(KNOWN_PORTS, self.port_items.values(), strict=True):
            mi.title = self._port_label(prt, default_name)
            mi.state = 1 if prt in self.ports else 0

    def _port_label(self, prt: int, default_name: str) -> str:
        detected = _detect_app(prt)
        name = detected or f"{default_name} (offline)"
        n = _state.read_counts().get(prt, 0)
        suffix = f": {n} approved" if n else ""
        return f"{name} ({prt}){suffix}"

    # ----- actions -------------------------------------------------------
    def _make_port_toggle(self, prt: int):
        def _cb(item: rumps.MenuItem) -> None:
            if prt in self.ports:
                if len(self.ports) == 1:
                    rumps.notification("Yes2All", "Cannot disable",
                                       "At least one port must remain enabled.")
                    item.state = 1
                    return
                self.ports = [p for p in self.ports if p != prt]
            else:
                self.ports = sorted(set(self.ports) | {prt})
            item.state = 1 if prt in self.ports else 0
            if _is_loaded():
                try:
                    svc.uninstall()
                    svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs)
                except Exception as e:  # noqa: BLE001
                    rumps.notification("Yes2All", "Reinstall failed", str(e))
                    return
                self._refresh_status()
                rumps.notification("Yes2All", "Ports updated", f"watching {self.ports}")
        return _cb

    # ----- actions -------------------------------------------------------
    def on_toggle(self, _: object) -> None:
        if _is_loaded():
            self.on_stop(None)
        else:
            self.on_start(None)

    def on_start(self, _: object) -> None:
        try:
            svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs)
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Start failed", str(e))
            return
        self._refresh_status()
        rumps.notification("Yes2All", "Started",
                           f"ports {self.ports}, every {self.interval}s, "
                           f"sweep={'on' if self.sweep_tabs else 'off'}")

    def on_stop(self, _: object) -> None:
        try:
            svc.uninstall()
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Stop failed", str(e))
            return
        self._refresh_status()
        rumps.notification("Yes2All", "Stopped", "watcher unloaded")

    def on_toggle_sweep(self, item: rumps.MenuItem) -> None:
        self.sweep_tabs = not self.sweep_tabs
        item.state = 1 if self.sweep_tabs else 0
        if _is_loaded():
            # Apply by reinstalling.
            try:
                svc.uninstall()
                svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs)
            except Exception as e:  # noqa: BLE001
                rumps.notification("Yes2All", "Reinstall failed", str(e))
                return
            self._refresh_status()

    def on_open_log(self, _: object) -> None:
        if not LOG_OUT.exists():
            LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
            LOG_OUT.touch()
        # Open Terminal.app with `tail -f` on the log file.
        script = f'tell application "Terminal" to do script "tail -f {LOG_OUT}"\n' \
                 f'tell application "Terminal" to activate'
        subprocess.run(["osascript", "-e", script], check=False)

    def _interval_title(self) -> str:
        return f"Interval: {self.interval}s\u2026"

    def _reinstall_if_loaded(self) -> bool:
        if not _is_loaded():
            return False
        try:
            svc.uninstall()
            svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs)
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Reinstall failed", str(e))
            return False
        return True

    def on_add_port(self, _: object) -> None:
        win = rumps.Window(
            title="Add CDP port",
            message="Enter a TCP port (1\u201365535) where Cursor or VS Code is\n"
                    "running with --remote-debugging-port=<port>.",
            default_text="9444",
            ok="Add",
            cancel="Cancel",
            dimensions=(120, 22),
        )
        win.icon = ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK
        resp = win.run()
        if not resp.clicked:
            return
        try:
            prt = int(resp.text.strip())
            if not (1 <= prt <= 65535):
                raise ValueError
        except ValueError:
            rumps.alert("Invalid port", "Please enter an integer between 1 and 65535.")
            return
        if prt in self.ports:
            rumps.notification("Yes2All", "Already watching", f"port {prt}")
            return
        self.ports = sorted(set(self.ports) | {prt})
        # If this port isn't in KNOWN_PORTS there is no checkbox for it,
        # but the watcher will still poll it. About dialog reflects all ports.
        if self._reinstall_if_loaded():
            rumps.notification("Yes2All", "Port added", f"watching {self.ports}")
        else:
            rumps.notification("Yes2All", "Port added",
                               f"will watch {self.ports} once started")
        self._refresh_status()

    def on_reset_counters(self, _: object) -> None:
        _state.write_counts({})
        self._last_total = 0
        self._refresh_status()

    def on_set_interval(self, _: object) -> None:
        win = rumps.Window(
            title="Set poll interval",
            message="Seconds between polls (e.g. 0.5). Lower = snappier, more CPU.",
            default_text=str(self.interval),
            ok="Apply",
            cancel="Cancel",
            dimensions=(120, 22),
        )
        win.icon = ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK
        resp = win.run()
        if not resp.clicked:
            return
        try:
            val = float(resp.text.strip())
            if not (0.05 <= val <= 60.0):
                raise ValueError
        except ValueError:
            rumps.alert("Invalid interval", "Enter a number between 0.05 and 60 seconds.")
            return
        self.interval = val
        self.interval_item.title = self._interval_title()
        if self._reinstall_if_loaded():
            rumps.notification("Yes2All", "Interval updated", f"{self.interval}s")

    def on_about(self, _: object) -> None:
        try:
            from importlib.metadata import version as _pkg_version
            ver = _pkg_version("yes2all")
        except Exception:
            ver = "dev"
        loaded = _is_loaded()
        ports_str = ", ".join(str(p) for p in self.ports) or "(none)"
        msg = (
            f"Yes2All v{ver}\n"
            f"Auto-approves agent tool prompts in Cursor / VS Code via CDP.\n\n"
            f"Watcher: {'running' if loaded else 'stopped'}\n"
            f"Ports:   {ports_str}\n"
            f"Interval: {self.interval}s\n"
            f"Sweep tabs: {'on' if self.sweep_tabs else 'off'}"
        )
        rumps.alert(title="About Yes2All", message=msg, ok="OK",
                    icon_path=ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK)

    def on_quit(self, _: object) -> None:
        # Stop the watcher first, then quit the menu-bar app itself.
        # Also remove the menu-bar LaunchAgent so launchd won't immediately
        # respawn this process (KeepAlive=true).
        try:
            if _is_loaded():
                svc.uninstall()
        except Exception:
            pass
        try:
            svc.menubar_uninstall()
        except Exception:
            pass
        rumps.quit_application()


def run() -> None:
    Yes2AllApp().run()
