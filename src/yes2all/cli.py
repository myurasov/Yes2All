# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""Yes2All CLI."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

import typer

from . import service as svc
from . import state as _state
from .cdp import CDPSession, list_pages, list_targets
from .finder import (
    CLICK_CHAT_CONFIRMATION_JS,
    CLICK_CHAT_QUESTION_JS,
    CLICK_CLAUDE_PROMPT_JS,
    CLICK_CODEX_PROMPT_JS,
    CLICK_FIRST_APPROVAL_JS,
    FIND_APPROVAL_BUTTONS_JS,
    SWEEP_TABS_AND_CLICK_JS,
    countdown_claude_js,
    countdown_codex_js,
    countdown_js,
)

app = typer.Typer(add_completion=False, help="Auto-approve agent tool prompts in Cursor / VS Code.")
service_app = typer.Typer(help="Manage the Yes2All background service.")
app.add_typer(service_app, name="service")


@app.command()
def targets(
    port: Annotated[int, typer.Option(help="CDP remote-debugging-port")] = 9222,
) -> None:
    """List all CDP targets exposed by the editor."""

    async def _run() -> None:
        ts = await list_targets(port=port)
        for t in ts:
            print(f"{t.type:8s} {t.title[:60]:60s} {t.url[:80]}")

    asyncio.run(_run())


@app.command()
def probe(
    port: Annotated[int, typer.Option(help="CDP remote-debugging-port")] = 9222,
    click: Annotated[bool, typer.Option(help="Click the first matching button")] = False,
) -> None:
    """Find approval buttons (Run/Allow/Approve/Accept) on every page target."""

    async def _run() -> None:
        pages = await list_pages(port=port)
        if not pages:
            print("No page targets found.")
            return
        js = CLICK_FIRST_APPROVAL_JS if click else FIND_APPROVAL_BUTTONS_JS
        total = 0
        for p in pages:
            print(f"\n[page] {p.title}")
            try:
                async with CDPSession(p.ws_url) as s:
                    raw = await s.evaluate(js)
            except Exception as e:  # noqa: BLE001 — surface any CDP error to the user
                print(f"  error: {e}")
                continue
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                print(f"  unexpected result: {raw!r}")
                continue
            count = data.get("count", 0)
            total += count
            print(f"  url: {data.get('url', '')[:120]}")
            print(f"  matches: {count}")
            for b in data.get("buttons", []):
                print(
                    f"    - <{b['tag']}> text={b['text']!r} aria={b['ariaLabel']!r} "
                    f"role={b['role']} rect={b['rect']} classes={b['classes'][:80]!r}"
                )
        print(f"\nTotal approval buttons found: {total}")

    asyncio.run(_run())


@app.command()
def watch(
    port: Annotated[
        list[int],
        typer.Option("--port", help="CDP remote-debugging-port (repeat for multiple)."),
    ] = [9222],
    interval: Annotated[float, typer.Option(help="Poll interval (seconds)")] = 1,
    once: Annotated[bool, typer.Option(help="Exit after first successful click")] = False,
    sweep_tabs: Annotated[
        bool,
        typer.Option(
            "--sweep-tabs/--no-sweep-tabs",
            help="Cycle inactive Cursor chat tabs to find pending approvals (restores original tab afterwards).",
        ),
    ] = False,
    countdown: Annotated[
        float,
        typer.Option(help="Seconds to show countdown badge before clicking (0=instant)."),
    ] = 3,
) -> None:
    """Poll page targets and auto-click approval buttons as they appear."""
    use_countdown = countdown > 0
    js = SWEEP_TABS_AND_CLICK_JS if sweep_tabs else CLICK_FIRST_APPROVAL_JS
    js_cd = countdown_js(countdown) if use_countdown else ""
    js_cd_codex = countdown_codex_js(countdown) if use_countdown else ""
    js_cd_claude = countdown_claude_js(countdown) if use_countdown else ""
    ports = list(port) if port else [9222]

    def _summarize_click(p_title: str, data: dict) -> int:
        ts = time.strftime("%H:%M:%S")
        # Sweep payload: {clicked: N, results: [{tab, clicked}]}.
        if "results" in data:
            n = data.get("clicked", 0) or 0
            for r in data.get("results", []):
                if r.get("clicked"):
                    b = r["clicked"]
                    tool = b.get("tool") or "?"
                    print(
                        f"[{ts}] CLICKED on '{p_title[:40]}' tab={r['tab'][:40]!r} "
                        f"tool={tool!r} <{b['tag']}> rect={b['rect']}",
                        flush=True,
                    )
            return int(n)
        # Active-tab-only payload: {count, buttons}.
        if data.get("count"):
            b = data["buttons"][0]
            tool = b.get("tool") or "?"
            print(
                f"[{ts}] CLICKED on '{p_title[:40]}' (active) tool={tool!r} <{b['tag']}> rect={b['rect']}",
                flush=True,
            )
            return 1
        return 0

    async def _run() -> None:
        print(
            f"watching ports {ports} every {interval}s "
            f"(once={once}, sweep_tabs={sweep_tabs}, countdown={countdown}s) ...",
            flush=True,
        )
        while True:
            for prt in ports:
                try:
                    pages = await list_pages(port=prt)
                except Exception as e:
                    print(f"  [port {prt}] list_pages error: {e}", flush=True)
                    continue
                for p in pages:
                    if use_countdown:
                        # Countdown mode: single JS handles detect + badge + click.
                        try:
                            async with CDPSession(p.ws_url) as s:
                                raw_cd = await s.evaluate(js_cd)
                        except Exception as e:
                            print(f"  [{prt}/{p.title[:40]}] error: {e}", flush=True)
                            continue
                        try:
                            data_cd = json.loads(raw_cd) if isinstance(raw_cd, str) else raw_cd
                        except Exception:
                            data_cd = {}
                        cd_n = int(data_cd.get("count", 0) or 0)
                        cd_pending = int(data_cd.get("pending", 0) or 0)
                        if cd_n:
                            ts = time.strftime("%H:%M:%S")
                            for r in data_cd.get("clicked", []):
                                print(
                                    f"[{ts}] CLICKED (countdown) on '{prt}/{p.title[:40]}' text={r.get('text')!r}",
                                    flush=True,
                                )
                            _state.add_clicks(prt, cd_n)
                            if once:
                                return
                    else:
                        # Instant mode: existing handlers.
                        try:
                            async with CDPSession(p.ws_url) as s:
                                raw = await s.evaluate(js)
                                raw_cq = await s.evaluate(CLICK_CHAT_QUESTION_JS)
                                raw_cc = await s.evaluate(CLICK_CHAT_CONFIRMATION_JS)
                        except Exception as e:
                            print(f"  [{prt}/{p.title[:40]}] error: {e}", flush=True)
                            continue
                        try:
                            data = json.loads(raw) if isinstance(raw, str) else raw
                        except Exception:
                            data = {}
                        try:
                            data_cq = json.loads(raw_cq) if isinstance(raw_cq, str) else raw_cq
                        except Exception:
                            data_cq = {}
                        try:
                            data_cc = json.loads(raw_cc) if isinstance(raw_cc, str) else raw_cc
                        except Exception:
                            data_cc = {}
                        p_label = f"{prt}/{p.title}"
                        clicked = _summarize_click(p_label, data)
                        cq_n = int(data_cq.get("count", 0) or 0)
                        if cq_n:
                            ts = time.strftime("%H:%M:%S")
                            for r in data_cq.get("results", []):
                                print(
                                    f"[{ts}] CHAT-QUESTION on '{p_label[:50]}' "
                                    f"question={r.get('question')!r} "
                                    f"option={r.get('label')!r} via={r.get('how')}",
                                    flush=True,
                                )
                        cc_n = int(data_cc.get("count", 0) or 0)
                        if cc_n:
                            ts = time.strftime("%H:%M:%S")
                            for r in data_cc.get("results", []):
                                print(
                                    f"[{ts}] CHAT-CONFIRMATION on '{p_label[:50]}' "
                                    f"button={r.get('label')!r} dialog={r.get('dialog')!r}",
                                    flush=True,
                                )
                        if (clicked or cq_n or cc_n) and once:
                            _state.add_clicks(prt, int(clicked) + cq_n + cc_n)
                            return
                        _state.add_clicks(prt, int(clicked) + cq_n + cc_n)
                # Scan iframe targets for Codex/Claude prompts (webview-hosted UI).
                try:
                    all_targets = await list_targets(port=prt)
                except Exception:
                    all_targets = []
                for t in all_targets:
                    if t.type != "iframe" or not t.ws_url:
                        continue
                    # Run Codex handler.
                    codex_js = js_cd_codex if use_countdown else CLICK_CODEX_PROMPT_JS
                    try:
                        async with CDPSession(t.ws_url) as s:
                            raw_cx = await s.evaluate(codex_js)
                    except Exception:
                        raw_cx = "{}"
                    try:
                        data_cx = json.loads(raw_cx) if isinstance(raw_cx, str) else raw_cx
                    except Exception:
                        data_cx = {}
                    cx_n = int(data_cx.get("count", 0) or 0)
                    if cx_n:
                        ts = time.strftime("%H:%M:%S")
                        cx_key = "clicked" if use_countdown else "results"
                        for r in data_cx.get(cx_key, []):
                            label = r.get("text") or r.get("label") or ""
                            print(
                                f"[{ts}] CODEX-PROMPT on '{prt}/{t.title[:50]}' option={label!r}",
                                flush=True,
                            )
                        _state.add_clicks(prt, cx_n)
                        if once:
                            return
                    # Run Claude handler.
                    claude_js = js_cd_claude if use_countdown else CLICK_CLAUDE_PROMPT_JS
                    try:
                        async with CDPSession(t.ws_url) as s:
                            raw_cl = await s.evaluate(claude_js)
                    except Exception:
                        raw_cl = "{}"
                    try:
                        data_cl = json.loads(raw_cl) if isinstance(raw_cl, str) else raw_cl
                    except Exception:
                        data_cl = {}
                    cl_n = int(data_cl.get("count", 0) or 0)
                    if cl_n:
                        ts = time.strftime("%H:%M:%S")
                        cl_key = "clicked" if use_countdown else "results"
                        for r in data_cl.get(cl_key, []):
                            label = r.get("text") or r.get("label") or ""
                            print(
                                f"[{ts}] CLAUDE-PROMPT on '{prt}/{t.title[:50]}' option={label!r}",
                                flush=True,
                            )
                        _state.add_clicks(prt, cl_n)
                        if once:
                            return
            await asyncio.sleep(interval)

    asyncio.run(_run())


@service_app.command("install")
def service_install(
    port: Annotated[
        list[int],
        typer.Option("--port", help="CDP remote-debugging-port (repeat for multiple)."),
    ] = [9222],
    interval: Annotated[float, typer.Option(help="Poll interval (seconds)")] = 1,
    sweep_tabs: Annotated[
        bool,
        typer.Option(
            "--sweep-tabs/--no-sweep-tabs",
            help="Cycle inactive Cursor chat tabs (switches tabs briefly).",
        ),
    ] = False,
    countdown: Annotated[
        float,
        typer.Option(help="Seconds to show countdown badge before clicking (0=instant)."),
    ] = 3,
) -> None:
    """Install + start Yes2All as a background service (launchd / systemd --user)."""
    svc.install(
        list(port) if port else [9222],
        interval,
        sweep_tabs=sweep_tabs,
        countdown=countdown,
    )


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the Yes2All background service."""
    svc.uninstall()


@service_app.command("status")
def service_status() -> None:
    """Show whether the Yes2All background service is loaded/running."""
    svc.status()


@app.command()
def menubar() -> None:
    """Run the macOS menu-bar app (foreground). Use `service install-menubar` to auto-start at login."""
    import sys

    if sys.platform != "darwin":
        typer.echo("Error: y2a-menubar is macOS-only.", err=True)
        raise typer.Exit(1)
    from . import menubar as mb

    mb.run()


@service_app.command("install-menubar")
def service_install_menubar() -> None:
    """Install a LaunchAgent that auto-starts the menu-bar app at login (macOS only)."""
    svc.menubar_install()


@service_app.command("uninstall-menubar")
def service_uninstall_menubar() -> None:
    """Remove the menu-bar auto-start LaunchAgent."""
    svc.menubar_uninstall()


if __name__ == "__main__":
    app()
