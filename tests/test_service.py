# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""service.py: plist/systemd generation and parse round-trips."""

from __future__ import annotations

import plistlib

import pytest

from yes2all import service as svc

SPACED_EXE = "/Users/someone/My iCloud Checkout/.venv/bin/yes2all"
SPACED_SRC = "/Users/someone/My iCloud Checkout/src"


@pytest.fixture(autouse=True)
def _fake_paths(monkeypatch):
    monkeypatch.setattr(svc, "_yes2all_executable", lambda: SPACED_EXE)
    monkeypatch.setattr(svc, "_src_dir", lambda: SPACED_SRC)


ARGSETS = [
    dict(
        ports=[9222],
        interval=1.0,
        sweep_tabs=False,
        countdown=0.0,
        resume_delay=0.0,
        ignore_user_questions=True,
        answer_text_questions=True,
    ),
    dict(
        ports=[9222, 9333],
        interval=0.5,
        sweep_tabs=True,
        countdown=3.0,
        resume_delay=5.0,
        ignore_user_questions=False,
        answer_text_questions=False,
    ),
]


@pytest.mark.parametrize("args", ARGSETS)
def test_launchd_plist_roundtrip(tmp_path, monkeypatch, args):
    plist_file = tmp_path / "com.yes2all.watcher.plist"
    monkeypatch.setattr(svc, "launchd_plist_path", lambda: plist_file)
    content = svc.launchd_plist(
        args["ports"],
        args["interval"],
        tmp_path / "logs",
        sweep_tabs=args["sweep_tabs"],
        countdown=args["countdown"],
        resume_delay=args["resume_delay"],
        ignore_user_questions=args["ignore_user_questions"],
        answer_text_questions=args["answer_text_questions"],
    )
    # Valid plist, exe with spaces survives intact as a single argv element.
    data = plistlib.loads(content.encode())
    assert data["ProgramArguments"][0] == SPACED_EXE
    assert data["EnvironmentVariables"]["PYTHONPATH"] == SPACED_SRC
    assert data["KeepAlive"] is True and data["RunAtLoad"] is True

    plist_file.write_text(content)
    parsed = svc.read_installed_args()
    assert parsed == {
        "ports": args["ports"],
        "interval": args["interval"],
        "sweep_tabs": args["sweep_tabs"],
        "countdown": args["countdown"],
        "resume_delay": args["resume_delay"],
        "ignore_user_questions": args["ignore_user_questions"],
        "answer_text_questions": args["answer_text_questions"],
    }


def test_read_installed_args_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "launchd_plist_path", lambda: tmp_path / "absent.plist")
    assert svc.read_installed_args() is None


@pytest.mark.parametrize("args", ARGSETS)
def test_systemd_unit_quotes_spaced_paths(args):
    unit = svc.systemd_unit(
        args["ports"],
        args["interval"],
        sweep_tabs=args["sweep_tabs"],
        countdown=args["countdown"],
        resume_delay=args["resume_delay"],
        ignore_user_questions=args["ignore_user_questions"],
        answer_text_questions=args["answer_text_questions"],
    )
    assert f'ExecStart="{SPACED_EXE}" watch' in unit
    assert f'Environment="PYTHONPATH={SPACED_SRC}"' in unit
    for p in args["ports"]:
        assert f"--port {p}" in unit
    assert ("--sweep-tabs" if args["sweep_tabs"] else "--no-sweep-tabs") in unit
    assert ("--answer-text-questions" if args["answer_text_questions"] else "--no-answer-text-questions") in unit


def test_menubar_plist_valid(tmp_path):
    data = plistlib.loads(svc._menubar_plist(tmp_path / "logs").encode())
    assert data["ProgramArguments"] == [SPACED_EXE, "menubar"]
    assert data["LimitLoadToSessionType"] == "Aqua"
