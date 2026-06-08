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


def _src_dir() -> str:
    """Directory that must be on PYTHONPATH for `yes2all` to import.

    Editable installs can fail to register the package on ``sys.path`` via the
    generated ``.pth`` file in some environments — notably an iCloud-synced
    project path containing spaces, where uv's ``_editable_impl_yes2all.pth``
    (a plain-path entry sorted before ``_virtualenv.pth``) is dropped during
    site initialization. Embedding ``PYTHONPATH`` in the launchd/systemd
    definition makes the background job import reliably regardless of the
    editable-install state. The value is the directory that contains the
    running ``yes2all`` package (i.e. ``<project>/src``).
    """
    import yes2all

    return str(Path(yes2all.__file__).resolve().parent.parent)


# ----- macOS launchd -----------------------------------------------------------


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def read_installed_args() -> dict | None:
    """Parse the installed launchd plist.

    Returns dict with keys ``ports``, ``interval``, ``sweep_tabs``, ``countdown``,
    ``max_defer``, ``ignore_user_questions`` (or ``None`` if no plist is
    installed / can't be parsed).
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
        max_defer = 0.0
        ignore_user_questions = True
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
            if a == "--max-defer" and i + 1 < len(args):
                try:
                    max_defer = float(args[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            if a == "--sweep-tabs":
                sweep_tabs = True
            elif a == "--no-sweep-tabs":
                sweep_tabs = False
            elif a == "--ignore-user-questions":
                ignore_user_questions = True
            elif a == "--no-ignore-user-questions":
                ignore_user_questions = False
            i += 1
        if not ports:
            ports = [9222]
        return {
            "ports": ports,
            "interval": interval,
            "sweep_tabs": sweep_tabs,
            "countdown": countdown,
            "max_defer": max_defer,
            "ignore_user_questions": ignore_user_questions,
        }
    except Exception:
        return None


def launchd_plist(
    ports: list[int],
    interval: float,
    log_dir: Path,
    sweep_tabs: bool = True,
    countdown: float = 0,
    max_defer: float = 0,
    ignore_user_questions: bool = True,
) -> str:
    exe = _yes2all_executable()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / "yes2all.out.log"
    stderr = log_dir / "yes2all.err.log"
    sweep_flag = "--sweep-tabs" if sweep_tabs else "--no-sweep-tabs"
    iuq_flag = "--ignore-user-questions" if ignore_user_questions else "--no-ignore-user-questions"
    port_args = "\n    ".join(f"<string>--port</string>   <string>{p}</string>" for p in ports)
    countdown_args = f"\n    <string>--countdown</string><string>{countdown}</string>"
    max_defer_args = f"\n    <string>--max-defer</string><string>{max_defer}</string>"
    iuq_args = f"\n    <string>{iuq_flag}</string>"
    src_dir = _src_dir()
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
    <string>{sweep_flag}</string>{countdown_args}{max_defer_args}{iuq_args}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>     <string>{src_dir}</string>
  </dict>
  <key>RunAtLoad</key>        <true/>
  <key>KeepAlive</key>        <true/>
  <key>StandardOutPath</key>  <string>{stdout}</string>
  <key>StandardErrorPath</key><string>{stderr}</string>
  <key>ProcessType</key>      <string>Background</string>
</dict>
</plist>
"""


def launchd_install(
    ports: list[int],
    interval: float,
    sweep_tabs: bool = True,
    countdown: float = 0,
    max_defer: float = 0,
    ignore_user_questions: bool = True,
) -> None:
    plist_path = launchd_plist_path()
    log_dir = Path.home() / "Library" / "Logs" / "yes2all"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        launchd_plist(
            ports,
            interval,
            log_dir,
            sweep_tabs=sweep_tabs,
            countdown=countdown,
            max_defer=max_defer,
            ignore_user_questions=ignore_user_questions,
        )
    )
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


def launchd_pid() -> int | None:
    """Return the watcher process PID if the LaunchAgent is loaded, else None.

    Parses `launchctl list <label>` output: looks for a `"PID" = <n>;` line.
    """
    r = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        s = line.strip().rstrip(";").strip()
        if s.startswith('"PID"'):
            _, _, rhs = s.partition("=")
            try:
                return int(rhs.strip())
            except ValueError:
                return None
    return None


def launchd_is_paused() -> bool:
    """Return True if the watcher process is currently SIGSTOP'd (state `T`)."""
    pid = launchd_pid()
    if pid is None:
        return False
    r = subprocess.run(["ps", "-p", str(pid), "-o", "state="], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False
    return r.stdout.strip().startswith("T")


def launchd_pause() -> None:
    """SIGSTOP the watcher process — keeps the LaunchAgent loaded but suspends work.

    Unlike `launchctl unload`, this doesn't remove the plist or let launchd
    respawn the process. SIGSTOP persists until SIGCONT.
    """
    pid = launchd_pid()
    if pid is None:
        raise RuntimeError("watcher is not running")
    r = subprocess.run(["kill", "-STOP", str(pid)], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"kill -STOP {pid} failed: {r.stderr.strip() or r.stdout.strip()}")


def launchd_resume() -> None:
    """SIGCONT the watcher process."""
    pid = launchd_pid()
    if pid is None:
        raise RuntimeError("watcher is not running")
    r = subprocess.run(["kill", "-CONT", str(pid)], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"kill -CONT {pid} failed: {r.stderr.strip() or r.stdout.strip()}")


# ----- macOS menu-bar app LaunchAgent -----------------------------------------

MENUBAR_LABEL = "com.yes2all.menubar"


def menubar_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MENUBAR_LABEL}.plist"


def _menubar_plist(log_dir: Path) -> str:
    exe = _yes2all_executable()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = log_dir / "menubar.out.log"
    stderr = log_dir / "menubar.err.log"
    src_dir = _src_dir()
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
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>     <string>{src_dir}</string>
  </dict>
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


def systemd_unit(
    ports: list[int],
    interval: float,
    sweep_tabs: bool = True,
    countdown: float = 0,
    max_defer: float = 0,
    ignore_user_questions: bool = True,
) -> str:
    exe = _yes2all_executable()
    sweep_flag = "--sweep-tabs" if sweep_tabs else "--no-sweep-tabs"
    iuq_flag = "--ignore-user-questions" if ignore_user_questions else "--no-ignore-user-questions"
    port_args = " ".join(f"--port {p}" for p in ports)
    countdown_arg = f" --countdown {countdown}"
    max_defer_arg = f" --max-defer {max_defer}"
    src_dir = _src_dir()
    return f"""[Unit]
Description=Yes2All — auto-approve agent tool prompts in Cursor / VS Code
After=graphical-session.target

[Service]
Environment=PYTHONPATH={src_dir}
ExecStart={exe} watch {port_args} --interval {interval} {sweep_flag}{countdown_arg}{max_defer_arg} {iuq_flag}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
"""


def systemd_install(
    ports: list[int],
    interval: float,
    sweep_tabs: bool = True,
    countdown: float = 0,
    max_defer: float = 0,
    ignore_user_questions: bool = True,
) -> None:
    unit_path = systemd_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        systemd_unit(
            ports,
            interval,
            sweep_tabs=sweep_tabs,
            countdown=countdown,
            max_defer=max_defer,
            ignore_user_questions=ignore_user_questions,
        )
    )
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


def install(
    ports: list[int],
    interval: float,
    sweep_tabs: bool = True,
    countdown: float = 0,
    max_defer: float = 0,
    ignore_user_questions: bool = True,
) -> None:
    sysname = platform.system()
    if sysname == "Darwin":
        launchd_install(
            ports,
            interval,
            sweep_tabs=sweep_tabs,
            countdown=countdown,
            max_defer=max_defer,
            ignore_user_questions=ignore_user_questions,
        )
    elif sysname == "Linux":
        systemd_install(
            ports,
            interval,
            sweep_tabs=sweep_tabs,
            countdown=countdown,
            max_defer=max_defer,
            ignore_user_questions=ignore_user_questions,
        )
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
