# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""Cross-process state shared between the watcher and menu-bar app.

Currently just a per-port counter of how many approval clicks the watcher has
made. Persisted as a small JSON file so the menu-bar process can read it back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

COUNTS_PATH = Path.home() / "Library" / "Application Support" / "yes2all" / "counts.json"


def read_counts() -> dict[int, int]:
    try:
        data = json.loads(COUNTS_PATH.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}
    out: dict[int, int] = {}
    for k, v in data.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def write_counts(counts: dict[int, int]) -> None:
    COUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = COUNTS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({str(k): int(v) for k, v in counts.items()}))
    os.replace(tmp, COUNTS_PATH)


def add_clicks(port: int, n: int) -> None:
    if n <= 0:
        return
    counts = read_counts()
    counts[port] = counts.get(port, 0) + n
    write_counts(counts)


# ----- menubar config persistence ---------------------------------------------

CONFIG_PATH = Path.home() / "Library" / "Application Support" / "yes2all" / "config.json"

_CONFIG_DEFAULTS: dict[str, object] = {
    "ports": [9222, 9333, 9444],
    "interval": 0.5,
    "sweep_tabs": True,
    "countdown": 0,
    "apps": [
        {"name": "Cursor", "app": "Cursor", "port": 9222},
        {"name": "VS Code", "app": "Visual Studio Code", "port": 9333},
    ],
}


def read_config() -> dict:
    """Read saved menubar config, falling back to defaults for missing keys."""
    cfg = dict(_CONFIG_DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text())
        if isinstance(data, dict):
            cfg.update(data)
    except (FileNotFoundError, ValueError, OSError):
        pass
    return cfg


def write_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    os.replace(tmp, CONFIG_PATH)
