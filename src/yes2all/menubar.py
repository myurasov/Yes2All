# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""macOS menu-bar app (y2a-menubar) to start/stop y2a-service.

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
from .state import read_config, write_config

_ASSETS = Path(__file__).parent / "assets"
# Two flat checkmark variants (loaded) + two open-circle variants (stopped).
# The menubar picks the pair based on system theme.
# We use @2x images and set logical size to 22x22 for retina sharpness.
ICON_DARK = str(_ASSETS / "icon-dark@2x.png")  # black check, for Light theme
ICON_LIGHT = str(_ASSETS / "icon-light@2x.png")  # white check, for Dark theme
ICON_OFF_DARK = str(_ASSETS / "icon-off-dark@2x.png")
ICON_OFF_LIGHT = str(_ASSETS / "icon-off-light@2x.png")
ICON_FLASH = str(_ASSETS / "icon-flash@2x.png")  # brief green pulse on click
ICON_LARGE_DARK = str(_ASSETS / "icon-large-dark.png")
ICON_LARGE_LIGHT = str(_ASSETS / "icon-large-light.png")

# Logical size for menubar icons (actual pixels are 2x for retina).
_ICON_SIZE = 22

# Duration of the green flash after a click is observed (seconds).
FLASH_DURATION = 0.45

LOG_OUT = Path.home() / "Library" / "Logs" / "yes2all" / "yes2all.out.log"


def _load_retina_icon(path: str) -> "NSImage":  # noqa: F821
    """Load a @2x PNG and set its logical size so macOS renders it at retina."""
    from AppKit import NSImage, NSSize  # type: ignore[import-not-found]

    img = NSImage.alloc().initWithContentsOfFile_(path)

    if img:
        img.setSize_(NSSize(_ICON_SIZE, _ICON_SIZE))
    return img


def _menu_icon(loaded: bool) -> str:
    if _system_is_dark():
        return ICON_LIGHT if loaded else ICON_OFF_LIGHT
    return ICON_DARK if loaded else ICON_OFF_DARK


def _system_is_dark() -> bool:
    """Return True if macOS is currently in Dark Mode."""
    try:
        r = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            check=False,
            timeout=0.5,
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
    @property  # type: ignore[override]
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, icon_path: str | None) -> None:
        self._icon = icon_path
        if icon_path is not None:
            self._icon_nsimage = _load_retina_icon(icon_path)
        else:
            self._icon_nsimage = None
        try:
            self._nsapp.setStatusBarIcon()
        except AttributeError:
            pass

    def __init__(self) -> None:
        super().__init__(
            "Yes2All",
            title=None,
            icon=None,
            template=False,
            quit_button=None,
        )
        self.icon = _menu_icon(_is_loaded())
        # Hydrate from saved config, then override from plist if running.
        cfg = read_config()
        plist_cfg = svc.read_installed_args()
        if plist_cfg:
            cfg.update(plist_cfg)
        self.ports: list[int] = cfg.get("ports") or [9222, 9333]
        self.interval: float = cfg.get("interval", 1)
        self.sweep_tabs: bool = cfg.get("sweep_tabs", True)
        self.countdown: float = cfg.get("countdown", 0)

        self.toggle_item = rumps.MenuItem("Start", callback=self.on_toggle)
        self.sweep_item = rumps.MenuItem("Cycle Cursor tabs", callback=self.on_toggle_sweep)
        self.sweep_item.state = 1 if self.sweep_tabs else 0

        # Flash state: when the watcher reports a click, briefly swap the
        # menubar icon to a green check.
        self._flash_until: float = 0.0
        self._last_total: int = sum(_state.read_counts().values())

        # One checkbox per known port, grouped under a "Ports" submenu.
        # Label is detected live from each port's /json/version endpoint.
        self.port_items: dict[int, rumps.MenuItem] = {}
        known_port_set = {p for p, _ in KNOWN_PORTS}
        for prt, default_name in KNOWN_PORTS:
            mi = rumps.MenuItem(
                self._port_label(prt, default_name),
                callback=self._make_port_toggle(prt),
            )
            mi.state = 1 if prt in self.ports else 0
            self.port_items[prt] = mi
        # Also create checkboxes for any extra ports from the plist.
        for prt in self.ports:
            if prt not in known_port_set:
                detected = _detect_app(prt) or f"Port {prt}"
                mi = rumps.MenuItem(f"{detected} ({prt})", callback=self._make_port_toggle(prt))
                mi.state = 1
                self.port_items[prt] = mi
        ports_menu = rumps.MenuItem("Watched Ports")
        for mi in self.port_items.values():
            ports_menu.add(mi)
        ports_menu.add(rumps.separator)
        ports_menu.add(rumps.MenuItem("Add Port…", callback=self.on_add_port))
        ports_menu.add(rumps.MenuItem("Reset counters", callback=self.on_reset_counters))
        self.interval_item = rumps.MenuItem(self._interval_title(), callback=self.on_set_interval)
        self.countdown_item = rumps.MenuItem(self._countdown_title(), callback=self.on_set_countdown)

        # App launchers — configurable list of editor apps + debug ports.
        self.apps: list[dict] = cfg.get("apps") or [
            {"name": "Cursor", "app": "Cursor", "port": 9222},
            {"name": "VS Code", "app": "Visual Studio Code", "port": 9333},
        ]
        self._launch_menu = rumps.MenuItem("Launch w/CDP")
        self._launch_items: list[rumps.MenuItem] = []
        self._launch_add_item = rumps.MenuItem("Add App…", callback=self.on_add_app)
        self._launch_edit_item = rumps.MenuItem("Edit Apps…", callback=self.on_edit_apps)
        # Populate launch menu (can't use clear() before rumps App.run()).
        for entry in self.apps:
            mi = rumps.MenuItem(self._launch_label(entry), callback=self._make_launch_cb(entry))
            self._launch_items.append(mi)
            self._launch_menu.add(mi)
        self._launch_menu.add(rumps.separator)
        self._launch_menu.add(self._launch_add_item)
        self._launch_menu.add(self._launch_edit_item)

        settings_menu = rumps.MenuItem("Settings")
        settings_menu.add(self.interval_item)
        settings_menu.add(self.countdown_item)
        settings_menu.add(self.sweep_item)

        self.menu = [
            self.toggle_item,
            None,
            settings_menu,
            self._launch_menu,
            ports_menu,
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
            self.countdown = cfg.get("countdown", 0)
            self.sweep_item.state = 1 if self.sweep_tabs else 0
            self.interval_item.title = self._interval_title()
            self.countdown_item.title = self._countdown_title()
        # Re-detect app on each known port and refresh checkbox label/state.
        known_ports_set = {p for p, _ in KNOWN_PORTS}
        for (prt, default_name), mi in zip(KNOWN_PORTS, [self.port_items[p] for p, _ in KNOWN_PORTS], strict=True):
            mi.title = self._port_label(prt, default_name)
            mi.state = 1 if prt in self.ports else 0
        # Also refresh dynamically-added ports.
        for prt, mi in self.port_items.items():
            if prt not in known_ports_set:
                detected = _detect_app(prt) or f"Port {prt}"
                n = _state.read_counts().get(prt, 0)
                suffix = f": {n} approved" if n else ""
                mi.title = f"{detected} ({prt}){suffix}"
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
                    rumps.notification(
                        "Yes2All",
                        "Cannot disable",
                        "At least one port must remain enabled.",
                    )
                    item.state = 1
                    return
                self.ports = [p for p in self.ports if p != prt]
            else:
                self.ports = sorted(set(self.ports) | {prt})
            item.state = 1 if prt in self.ports else 0
            self._save_config()
            if _is_loaded():
                try:
                    svc.uninstall()
                    svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs, countdown=self.countdown)
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
        self._save_config()
        try:
            svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs, countdown=self.countdown)
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Start failed", str(e))
            return
        self._refresh_status()
        rumps.notification(
            "Yes2All",
            "Started",
            f"ports {self.ports}, every {self.interval}s, cycle tabs={'on' if self.sweep_tabs else 'off'}",
        )

    def on_stop(self, _: object) -> None:
        try:
            svc.uninstall()
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Stop failed", str(e))
            return
        self._refresh_status()
        rumps.notification("Yes2All", "Stopped", "y2a-service unloaded")

    def on_toggle_sweep(self, item: rumps.MenuItem) -> None:
        self.sweep_tabs = not self.sweep_tabs
        item.state = 1 if self.sweep_tabs else 0
        self._save_config()
        if _is_loaded():
            # Apply by reinstalling.
            try:
                svc.uninstall()
                svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs, countdown=self.countdown)
            except Exception as e:  # noqa: BLE001
                rumps.notification("Yes2All", "Reinstall failed", str(e))
                return
            self._refresh_status()

    def on_open_log(self, _: object) -> None:
        if not LOG_OUT.exists():
            LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
            LOG_OUT.touch()
        # Open Terminal.app with `tail -f` on the log file.
        script = (
            f'tell application "Terminal" to do script "tail -f {LOG_OUT}"\ntell application "Terminal" to activate'
        )
        subprocess.run(["osascript", "-e", script], check=False)

    def _interval_title(self) -> str:
        return f"Interval: {self.interval}s\u2026"

    def _countdown_title(self) -> str:
        if self.countdown > 0:
            return f"Countdown: {self.countdown:.0f}s\u2026"
        return "Countdown: off\u2026"

    def _save_config(self) -> None:
        write_config(
            {
                "ports": self.ports,
                "interval": self.interval,
                "sweep_tabs": self.sweep_tabs,
                "countdown": self.countdown,
                "apps": self.apps,
            }
        )

    # ----- app launchers -------------------------------------------------
    @staticmethod
    def _launch_label(entry: dict) -> str:
        return f"{entry['name']} (:{entry['port']})"

    def _make_launch_cb(self, entry: dict):
        def _cb(_: rumps.MenuItem) -> None:
            app = entry["app"]
            port = entry["port"]
            try:
                subprocess.Popen(
                    ["open", "-a", app, "--args", f"--remote-debugging-port={port}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:  # noqa: BLE001
                rumps.notification("Yes2All", "Launch failed", str(e))

        return _cb

    def _rebuild_launch_menu(self) -> None:
        # Remove old dynamic items by title.
        for mi in self._launch_items:
            try:
                del self._launch_menu[mi.title]
            except KeyError:
                pass
        self._launch_items = []
        for entry in self.apps:
            mi = rumps.MenuItem(self._launch_label(entry), callback=self._make_launch_cb(entry))
            self._launch_items.append(mi)
            self._launch_menu.insert_before(self._launch_add_item, mi)

    def on_add_app(self, _: object) -> None:
        win = rumps.Window(
            title="Add App Launcher",
            message="Format: <display name>, <macOS app name>, <debug port>\nExample: Cursor, Cursor, 9222",
            default_text="",
            ok="Add",
            cancel="Cancel",
            dimensions=(260, 22),
        )
        win.icon = ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK
        resp = win.run()
        if not resp.clicked or not resp.text.strip():
            return
        parts = [s.strip() for s in resp.text.split(",")]
        if len(parts) != 3:
            rumps.alert("Invalid Format", "Expected: name, app, port")
            return
        try:
            port = int(parts[2])
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            rumps.alert("Invalid Port", "Port must be 1–65535.")
            return
        entry = {"name": parts[0], "app": parts[1], "port": port}
        self.apps.append(entry)
        self._rebuild_launch_menu()
        self._save_config()
        rumps.notification("Yes2All", "App added", self._launch_label(entry))

    def on_edit_apps(self, _: object) -> None:
        entries = "; ".join(f"{e['name']}, {e['app']}, {e['port']}" for e in self.apps)
        win = rumps.Window(
            title="Edit App Launchers",
            message="Semicolon-separated entries: name, app, port; name, app, port\n"
            "Example: Cursor, Cursor, 9222; VS Code, Visual Studio Code, 9333",
            default_text=entries,
            ok="Save",
            cancel="Cancel",
            dimensions=(360, 22),
        )
        win.icon = ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK
        resp = win.run()
        if not resp.clicked:
            return
        new_apps: list[dict] = []
        for chunk in resp.text.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = [s.strip() for s in chunk.split(",")]
            if len(parts) != 3:
                continue
            try:
                port = int(parts[2])
                if not (1 <= port <= 65535):
                    continue
            except ValueError:
                continue
            new_apps.append({"name": parts[0], "app": parts[1], "port": port})
        if not new_apps:
            rumps.alert("No Valid Apps", "At least one valid entry required.")
            return
        self.apps = new_apps
        self._rebuild_launch_menu()
        self._save_config()
        rumps.notification("Yes2All", "Apps updated", f"{len(self.apps)} app(s)")

    def _reinstall_if_loaded(self) -> bool:
        if not _is_loaded():
            return False
        try:
            svc.uninstall()
            svc.install(self.ports, self.interval, sweep_tabs=self.sweep_tabs, countdown=self.countdown)
        except Exception as e:  # noqa: BLE001
            rumps.notification("Yes2All", "Reinstall failed", str(e))
            return False
        return True

    def on_add_port(self, _: object) -> None:
        win = rumps.Window(
            title="Add CDP Port",
            message="Enter a TCP port (1\u201365535) where Cursor or VS Code is\n"
            "running with --remote-debugging-port=<port>.",
            default_text="9333",
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
            rumps.alert("Invalid Port", "Please enter an integer between 1 and 65535.")
            return
        if prt in self.ports:
            rumps.notification("Yes2All", "Already watching", f"port {prt}")
            return
        self.ports = sorted(set(self.ports) | {prt})

        # Add a dynamic checkbox menu item if this port isn't already known.
        if prt not in self.port_items:
            detected = _detect_app(prt) or f"Port {prt}"
            mi = rumps.MenuItem(f"{detected} ({prt})", callback=self._make_port_toggle(prt))
            mi.state = 1
            self.port_items[prt] = mi
            # Insert before the separator (after existing port checkboxes).
            self.menu["Ports"].insert_before(rumps.separator, mi)

        self._save_config()
        if self._reinstall_if_loaded():
            rumps.notification("Yes2All", "Port added", f"watching {self.ports}")
        else:
            rumps.notification("Yes2All", "Port added", f"will watch {self.ports} once started")
        self._refresh_status()

    def on_reset_counters(self, _: object) -> None:
        _state.write_counts({})
        self._last_total = 0
        self._refresh_status()

    def on_set_interval(self, _: object) -> None:
        win = rumps.Window(
            title="Set Poll Interval",
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
            rumps.alert("Invalid Interval", "Enter a number between 0.05 and 60 seconds.")
            return
        self.interval = val
        self.interval_item.title = self._interval_title()
        self._save_config()
        if self._reinstall_if_loaded():
            rumps.notification("Yes2All", "Interval updated", f"{self.interval}s")

    def on_set_countdown(self, _: object) -> None:
        win = rumps.Window(
            title="Set Countdown Before Click",
            message="Seconds to show countdown badge before auto-clicking.\nSet to 0 to disable (click immediately).",
            default_text=str(int(self.countdown) if self.countdown == int(self.countdown) else self.countdown),
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
            if not (0 <= val <= 300):
                raise ValueError
        except ValueError:
            rumps.alert("Invalid Countdown", "Enter a number between 0 and 300 seconds.")
            return
        self.countdown = val
        self.countdown_item.title = self._countdown_title()
        self._save_config()
        if self._reinstall_if_loaded():
            rumps.notification("Yes2All", "Countdown updated", self._countdown_title())

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
            f"Service: {'running' if loaded else 'stopped'}\n"
            f"Ports:   {ports_str}\n"
            f"Interval: {self.interval}s\n"
            f"Countdown: {self.countdown:.0f}s\n"
            f"Sweep tabs: {'on' if self.sweep_tabs else 'off'}\n\n"
            f"© Mikhail Yurasov <me@yurasov.me>\n"
            f"Apache License 2.0"
        )
        rumps.alert(
            title="About Yes2All",
            message=msg,
            ok="OK",
            icon_path=ICON_LARGE_LIGHT if _system_is_dark() else ICON_LARGE_DARK,
        )

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
