# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""Background service management for Yes2All (macOS launchd, Linux systemd --user)."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.yes2all.watcher"


def _yes2all_executable() -> str:
    """Resolve the absolute path to the installed `yes2all` console script."""
    exe = shutil.which("yes2all")
    if exe:
        return exe
    # Fallback: same dir as the python interpreter.
    candidate = Path(sys.executable).parent / "yes2all"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(
        "Could not locate the `yes2all` executable. Run `uv sync` first, then "
        "invoke `yes2all` from inside the project venv (e.g. `uv run yes2all service ...`)."
    )


# ----- macOS launchd -----------------------------------------------------------


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def read_installed_args() -> dict | None:
    """Parse the installed launchd plist and return {ports, interval, sweep_tabs, countdown}.

    Returns None if no plist is installed or it can't be parsed.
    """
    p = launchd_plist_path()
    if not p.exists():
        return None
    try:
        import plistlib

        with p.open("rb") as f:
            data = plistlib.load(f)
        args = data.get("ProgramArguments", [])
        ports: list[int] = []
        interval = 1
        sweep_tabs = True
        countdown = 0.0
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--port" and i + 1 < len(args):
                try:
                    ports.append(int(args[i + 1]))
                except ValueError:
                    pass
                i += 2
                continue
            if a == "--interval" and i + 1 < len(args):
                try:
                    interval = float(args[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            if a == "--countdown" and i + 1 < len(args):
                try:
                    countdown = float(args[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            if a == "--sweep-tabs":
                sweep_tabs = True
            elif a == "--no-sweep-tabs":
                sweep_tabs = False
            i += 1
        if not ports:
            ports = [9222]
        return {
            "ports": ports,
            "interval": interval,
            "sweep_tabs": sweep_tabs,
            "countdown": countdown,
        }
    except Exception:
        return None


def launchd_plist(
    ports: list[int],
    interval: float,
    log_dir: Path,
    sweep_tabs: bool = True,
    countdown: float = 0,
) -> str:
    exe = _yes2all_executable()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / "yes2all.out.log"
    stderr = log_dir / "yes2all.err.log"
    sweep_flag = "--sweep-tabs" if sweep_tabs else "--no-sweep-tabs"
    port_args = "\n    ".join(f"<string>--port</string>   <string>{p}</string>" for p in ports)
    countdown_args = f"\n    <string>--countdown</string><string>{countdown}</string>" if countdown > 0 else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exe}</string>
    <string>watch</string>
    {port_args}
    <string>--interval</string><string>{interval}</string>
    <string>{sweep_flag}</string>{countdown_args}
  </array>
  <key>RunAtLoad</key>        <true/>
  <key>KeepAlive</key>        <true/>
  <key>StandardOutPath</key>  <string>{stdout}</string>
  <key>StandardErrorPath</key><string>{stderr}</string>
  <key>ProcessType</key>      <string>Background</string>
</dict>
</plist>
"""


def launchd_install(ports: list[int], interval: float, sweep_tabs: bool = True, countdown: float = 0) -> None:
    plist_path = launchd_plist_path()
    log_dir = Path.home() / "Library" / "Logs" / "yes2all"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(launchd_plist(ports, interval, log_dir, sweep_tabs=sweep_tabs, countdown=countdown))
    print(f"wrote {plist_path}")
    # Reload if already loaded, then load.
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    r = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {r.stderr.strip() or r.stdout.strip()}")
    print(f"loaded launchd job {LABEL}")
    print(f"logs: {log_dir}")


def launchd_uninstall() -> None:
    plist_path = launchd_plist_path()
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        plist_path.unlink()
        print(f"removed {plist_path}")
    else:
        print(f"no plist at {plist_path}")


def launchd_status() -> None:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
    matches = [ln for ln in r.stdout.splitlines() if LABEL in ln]
    if matches:
        print("loaded:")
        for ln in matches:
            print(f"  {ln}")
    else:
        print(f"not loaded ({LABEL})")


# ----- macOS menu-bar app LaunchAgent -----------------------------------------

MENUBAR_LABEL = "com.yes2all.menubar"


def menubar_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MENUBAR_LABEL}.plist"


def _menubar_plist(log_dir: Path) -> str:
    exe = _yes2all_executable()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / "menubar.out.log"
    stderr = log_dir / "menubar.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>{MENUBAR_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exe}</string>
    <string>menubar</string>
  </array>
  <key>RunAtLoad</key>        <true/>
  <key>KeepAlive</key>        <true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key>  <string>{stdout}</string>
  <key>StandardErrorPath</key><string>{stderr}</string>
</dict>
</plist>
"""


def menubar_install() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Menu-bar app is macOS-only.")
    plist_path = menubar_plist_path()
    log_dir = Path.home() / "Library" / "Logs" / "yes2all"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_menubar_plist(log_dir))
    print(f"wrote {plist_path}")
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    r = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {r.stderr.strip() or r.stdout.strip()}")
    print(f"loaded launchd job {MENUBAR_LABEL}")


def menubar_uninstall() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Menu-bar app is macOS-only.")
    plist_path = menubar_plist_path()
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        plist_path.unlink()
        print(f"removed {plist_path}")
    else:
        print(f"no plist at {plist_path}")


# ----- Linux systemd --user ---------------------------------------------------


def systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{LABEL}.service"


def systemd_unit(ports: list[int], interval: float, sweep_tabs: bool = True, countdown: float = 0) -> str:
    exe = _yes2all_executable()
    sweep_flag = "--sweep-tabs" if sweep_tabs else "--no-sweep-tabs"
    port_args = " ".join(f"--port {p}" for p in ports)
    countdown_arg = f" --countdown {countdown}" if countdown > 0 else ""
    return f"""[Unit]
Description=Yes2All — auto-approve agent tool prompts in Cursor / VS Code
After=graphical-session.target

[Service]
ExecStart={exe} watch {port_args} --interval {interval} {sweep_flag}{countdown_arg}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
"""


def systemd_install(ports: list[int], interval: float, sweep_tabs: bool = True, countdown: float = 0) -> None:
    unit_path = systemd_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(systemd_unit(ports, interval, sweep_tabs=sweep_tabs, countdown=countdown))
    print(f"wrote {unit_path}")
    for cmd in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", f"{LABEL}.service"],
    ):
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr.strip()}")
    print(f"enabled+started {LABEL}.service")


def systemd_uninstall() -> None:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{LABEL}.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    p = systemd_unit_path()
    if p.exists():
        p.unlink()
        print(f"removed {p}")
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def systemd_status() -> None:
    subprocess.run(["systemctl", "--user", "status", f"{LABEL}.service", "--no-pager"], check=False)


# ----- dispatch ---------------------------------------------------------------


def install(ports: list[int], interval: float, sweep_tabs: bool = True, countdown: float = 0) -> None:
    sysname = platform.system()
    if sysname == "Darwin":
        launchd_install(ports, interval, sweep_tabs=sweep_tabs, countdown=countdown)
    elif sysname == "Linux":
        systemd_install(ports, interval, sweep_tabs=sweep_tabs, countdown=countdown)
    else:
        raise RuntimeError(
            f"Unsupported platform for service install: {sysname}. On Windows, use Task Scheduler manually for now."
        )


def uninstall() -> None:
    sysname = platform.system()
    if sysname == "Darwin":
        launchd_uninstall()
    elif sysname == "Linux":
        systemd_uninstall()
    else:
        raise RuntimeError(f"Unsupported platform: {sysname}")


def status() -> None:
    sysname = platform.system()
    if sysname == "Darwin":
        launchd_status()
    elif sysname == "Linux":
        systemd_status()
    else:
        raise RuntimeError(f"Unsupported platform: {sysname}")
