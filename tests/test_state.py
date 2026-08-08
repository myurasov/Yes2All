# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""state.py: counts/config persistence round-trips and corrupt-file handling."""

from __future__ import annotations

from yes2all import state


def test_counts_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "COUNTS_PATH", tmp_path / "counts.json")
    assert state.read_counts() == {}
    state.add_clicks(9222, 3)
    state.add_clicks(9333, 1)
    state.add_clicks(9222, 2)
    assert state.read_counts() == {9222: 5, 9333: 1}
    state.add_clicks(9222, 0)  # no-op
    assert state.read_counts() == {9222: 5, 9333: 1}


def test_counts_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "counts.json"
    monkeypatch.setattr(state, "COUNTS_PATH", p)
    p.write_text("{not json")
    assert state.read_counts() == {}
    p.write_text('{"9222": "junk", "9333": 4}')
    assert state.read_counts() == {9333: 4}


def test_config_defaults_and_merge(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(state, "CONFIG_PATH", p)
    cfg = state.read_config()
    assert cfg["ports"] == [9222, 9333]
    assert cfg["sweep_tabs"] is False
    assert cfg["ignore_user_questions"] is True
    assert cfg["answer_text_questions"] is True
    state.write_config({**cfg, "interval": 0.25, "ports": [9222]})
    cfg2 = state.read_config()
    assert cfg2["interval"] == 0.25
    assert cfg2["ports"] == [9222]
    # Missing keys still fall back to defaults.
    assert cfg2["countdown"] == 3


def test_defer_roundtrip_and_staleness(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "DEFER_PATH", tmp_path / "defer.json")
    assert state.read_defer() is False  # no file yet
    state.write_defer([9222])
    assert state.read_defer() is True
    state.write_defer([])
    assert state.read_defer() is False  # empty port list = not deferring
    state.write_defer([9222, 9333])
    assert state.read_defer(max_age=0.0) is False  # stale stamp ignored


def test_defer_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "defer.json"
    monkeypatch.setattr(state, "DEFER_PATH", p)
    p.write_text("{bad")
    assert state.read_defer() is False
    p.write_text('{"ports": [9222], "ts": "junk"}')
    assert state.read_defer() is False


def test_config_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(state, "CONFIG_PATH", p)
    p.write_text("]]]")
    assert state.read_config()["ports"] == [9222, 9333]
