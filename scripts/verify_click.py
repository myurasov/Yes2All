# Copyright 2026 Mikhail Yurasov <me@yurasov.me>
# SPDX-License-Identifier: Apache-2.0

"""End-to-end verification: inject a synthetic approval button into the live
editor, run the click path, and confirm the click handler fired.

This proves the finder + clicker work against Cursor's DOM model without
requiring a real pending tool-call approval.
"""

from __future__ import annotations

import asyncio
import json
import sys

from yes2all.cdp import CDPSession, list_pages
from yes2all.finder import CLICK_FIRST_APPROVAL_JS

INJECT_JS = r"""
(() => {
  // Remove any prior fixture.
  const prior = document.getElementById("__y2a_test_btn");
  if (prior) prior.remove();
  window.__y2a_test_clicked = false;

  // Mimic Cursor's real approval button structure.
  const btn = document.createElement("div");
  btn.id = "__y2a_test_btn";
  btn.className = "anysphere-button composer-run-button";
  btn.style.cssText = "position:fixed; left:10px; bottom:10px; z-index:99999; padding:6px 10px; background:#2d6cdf; color:#fff; cursor:pointer;";

  const wrap = document.createElement("span");
  wrap.className = "inline-flex items-baseline gap-[2px] min-w-0 overflow-hidden";
  const lbl = document.createElement("span");
  lbl.className = "truncate";
  lbl.textContent = "Run";
  wrap.appendChild(lbl);
  btn.appendChild(wrap);

  btn.addEventListener("click", () => { window.__y2a_test_clicked = true; });
  document.body.appendChild(btn);
  return "injected";
})()
"""

CHECK_JS = r"""
(() => JSON.stringify({
  clicked: !!window.__y2a_test_clicked,
  exists: !!document.getElementById("__y2a_test_btn"),
}))()
"""

CLEANUP_JS = r"""
(() => { const e=document.getElementById("__y2a_test_btn"); if(e) e.remove(); return "ok"; })()
"""


async def main() -> int:
    pages = await list_pages(port=9222)
    if not pages:
        print("FAIL: no page targets on 9222", file=sys.stderr)
        return 2
    p = pages[0]
    print(f"target: {p.title!r}")

    async with CDPSession(p.ws_url) as s:
        await s.send("Runtime.enable")

        await s.evaluate(INJECT_JS)
        print("injected synthetic Run button")

        click_raw = await s.evaluate(CLICK_FIRST_APPROVAL_JS)
        click_data = json.loads(click_raw) if isinstance(click_raw, str) else click_raw
        print(
            f"click result: count={click_data.get('count')} buttons={click_data.get('buttons')}"
        )

        # Give the click handler a moment to run.
        await asyncio.sleep(0.1)

        check_raw = await s.evaluate(CHECK_JS)
        check = json.loads(check_raw) if isinstance(check_raw, str) else check_raw
        print(f"verification: {check}")

        await s.evaluate(CLEANUP_JS)

    if check.get("clicked"):
        print("PASS — synthetic Run button was clicked by yes2all.")
        return 0
    print("FAIL — finder/click path did not fire handler.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
