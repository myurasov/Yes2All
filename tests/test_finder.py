# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""finder.py: placeholder substitution + JS validity guarantees.

These tests exist because the click variants are built by string surgery on
the find variant: a silent substitution failure produces a watcher that logs
CLICKED without ever clicking.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from yes2all import finder

PREP_HANDLERS = {
    name: js
    for name, js in finder._ALL_HANDLERS.items()  # noqa: SLF001 — test of module internals
}


def _fully_prepped(js: str) -> str:
    """Apply every runtime substitution the CLI applies."""
    js = finder.with_max_defer(js, 300)
    js = finder.with_ignore_user_questions(js, True)
    js = js.replace("__COUNTDOWN_SECS__", "3.0")
    return js


def test_no_unexpanded_lib_tokens():
    for name, js in PREP_HANDLERS.items():
        for token in ("__Y2A_TYPING_GUARD_FNS__", "__Y2A_FOCUS_GUARD__", "__Y2A_REAL_CLICK_FN__"):
            assert token not in js, f"{name} still contains {token}"


def test_no_placeholders_after_prep():
    for name, js in PREP_HANDLERS.items():
        prepped = _fully_prepped(js)
        for ph in ("__MAX_DEFER_MS__", "__Y2A_IGNORE_USER_QUESTIONS__", "__COUNTDOWN_SECS__"):
            assert ph not in prepped, f"{name} leaves {ph} unsubstituted"


def test_click_variant_actually_clicks():
    assert finder.CLICK_FIRST_APPROVAL_JS != finder.FIND_APPROVAL_BUTTONS_JS
    assert "const __DEFER_IF_TYPING = true;" in finder.CLICK_FIRST_APPROVAL_JS
    assert "const __DEFER_IF_TYPING = false;" in finder.FIND_APPROVAL_BUTTONS_JS
    assert "pointerdown" in finder.CLICK_FIRST_APPROVAL_JS


def test_every_clicking_handler_uses_pointer_sequence():
    for name, js in PREP_HANDLERS.items():
        if "realClick" in js:
            assert "__y2aRealClick" in js, f"{name} has a realClick not routed through __y2aRealClick"
            assert "pointerdown" in js, f"{name} clicks without PointerEvent (Cursor 3.3+ ignores it)"


def test_iframe_handlers_have_typing_guard():
    """Claude/Codex webview handlers must defer while the user types in the panel.

    The guard must be focus-aware (hasFocus) — activeElement alone persists
    after focus leaves the doc and would defer every click by max-defer.
    """
    for name in (
        "CLICK_CLAUDE_PROMPT_JS",
        "COUNTDOWN_CLAUDE_BADGE_JS",
        "CLICK_CODEX_PROMPT_JS",
        "COUNTDOWN_CODEX_BADGE_JS",
    ):
        js = PREP_HANDLERS[name]
        assert "__y2aDocTyping" in js, f"{name} missing iframe typing guard"
        assert "hasFocus" in js, f"{name} typing guard is not focus-aware"
        assert "shouldDeferForTyping()" in js, f"{name} never consults the defer guard"
        assert "__MAX_DEFER_MS__" in js, f"{name} lost the max-defer placeholder"


def test_page_handlers_report_typing():
    for name in ("FIND_APPROVAL_BUTTONS_JS", "COUNTDOWN_BADGE_JS", "SWEEP_TABS_AND_CLICK_JS"):
        assert "typing: userIsTyping()" in PREP_HANDLERS[name], f"{name} does not report typing state"


def test_text_confirm_has_typing_guard():
    assert "shouldDeferForTyping" in finder.DETECT_CHAT_TEXT_CONFIRM_JS
    assert "__MAX_DEFER_MS__" in finder.DETECT_CHAT_TEXT_CONFIRM_JS


def test_max_defer_zero_disables():
    js = finder.with_max_defer(finder.CLICK_CHAT_QUESTION_JS, 0)
    assert "const __Y2A_MAX_DEFER_MS = 0;" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_syntax_via_node(tmp_path):
    for name, js in PREP_HANDLERS.items():
        prepped = _fully_prepped(js)
        f = tmp_path / f"{name}.js"
        f.write_text(prepped)
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name} fails node --check:\n{r.stderr}"
