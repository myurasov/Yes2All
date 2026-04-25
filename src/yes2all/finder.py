"""Locate (and optionally click) the agent-tool approval 'Run' button in Cursor / VS Code."""
from __future__ import annotations

# JavaScript executed inside the editor's renderer to find approval buttons.
# We look for clickable elements whose visible text exactly matches one of the
# approval verbs, are visible (non-zero box, not aria-hidden), and aren't
# disabled. We also walk shadow DOM and same-origin iframes.
FIND_APPROVAL_BUTTONS_JS = r"""
(() => {
  const VERBS = ["Run", "Allow", "Approve", "Accept", "Yes"];
  const results = [];

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
    if (el.hasAttribute && el.hasAttribute("disabled")) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    const cs = el.ownerDocument.defaultView.getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0)
      return false;
    return true;
  }

  function* walk(root) {
    // Walk root's descendants, descending into open shadow roots and same-origin iframes.
    const stack = [root];
    while (stack.length) {
      const node = stack.pop();
      if (!node) continue;
      yield node;
      if (node.shadowRoot) stack.push(node.shadowRoot);
      const kids = node.children || [];
      for (let i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
      if (node.tagName === "IFRAME") {
        try {
          const doc = node.contentDocument;
          if (doc) stack.push(doc.documentElement);
        } catch (_) {}
      }
    }
  }

  function textOf(el) {
    // innerText if available, else textContent, trimmed.
    const t = (el.innerText || el.textContent || "").trim();
    return t;
  }

  // Strip trailing keyboard-shortcut glyphs (⌥ ⌘ ⇧ ⏎ arrows etc.) and
  // return the first whitespace-separated word so "Run⌥⌘Y" matches "Run".
  function firstWord(t) {
    if (!t) return t;
    // First line, then first run of letters.
    const line = t.split(/[\s\n\r]+/)[0] || "";
    const m = line.match(/^[A-Za-z]+/);
    return m ? m[0] : line;
  }

  // Class fragments seen on clickable approval buttons across editor builds.
  const CLICKABLE_CLASS_FRAGMENTS = [
    "monaco-button", "action-label",
    "anysphere-button", "composer-run-button",
    "ui-button", "ui-shell-tool-call__run-btn",
  ];

  function looksClickable(el) {
    if (!(el instanceof Element)) return false;
    const tag = el.tagName;
    if (tag === "BUTTON") return true;
    const role = el.getAttribute("role") || "";
    if (role === "button") return true;
    if (el.classList) {
      for (const c of CLICKABLE_CLASS_FRAGMENTS) {
        if (el.classList.contains(c)) return true;
      }
    }
    return false;
  }

  // The verb text often lives inside a nested <span>; bubble the match up to
  // the nearest clickable ancestor so we click the actual button, not the span.
  function clickableAncestor(el) {
    let cur = el;
    for (let i = 0; i < 8 && cur; i++) {
      if (looksClickable(cur)) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  function describe(el) {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      text: textOf(el).slice(0, 80),
      role: el.getAttribute("role") || null,
      ariaLabel: el.getAttribute("aria-label") || null,
      classes: (el.className && el.className.toString) ? el.className.toString().slice(0, 200) : "",
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      cx: Math.round(r.x + r.width / 2),
      cy: Math.round(r.y + r.height / 2),
    };
  }

  const seen = new Set();
  for (const node of walk(document.documentElement)) {
    if (!(node instanceof Element)) continue;
    const txt = textOf(node);
    if (!txt) continue;
    const word = firstWord(txt);
    if (!VERBS.includes(word)) continue;
    // Avoid matching giant text containers: cap visible text length at 40 chars
    // so we don't match an entire chat message that happens to start with "Run".
    if (txt.length > 40) continue;
    const target = clickableAncestor(node);
    if (!target) continue;
    if (seen.has(target)) continue;
    seen.add(target);
    if (!visible(target)) continue;
    results.push(describe(target));
  }
  return JSON.stringify({ url: location.href, count: results.length, buttons: results });
})()
"""


CLICK_FIRST_APPROVAL_JS = FIND_APPROVAL_BUTTONS_JS.replace(
    "results.push(describe(target));",
    "results.push(describe(target)); target.click(); break;",
)


# VS Code Copilot Chat renders tool-confirmation prompts as a "carousel" widget
# (`div.chat-question-carousel-container`). It's a listbox of numbered options
# with a Submit button; affirmative is typically option #1 (e.g. "Yes, run it").
# This DOM is in the main page (not inside a webview), so CDP can drive it.
CLICK_CHAT_QUESTION_JS = r"""
(() => {
  const POSITIVE = /^(yes|allow|approve|accept|run|continue|confirm|ok)\b/i;
  const NEGATIVE = /^(no|stop|cancel|deny|reject|skip)\b/i;

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0) return false;
    return true;
  }
  function fire(el, type, init) {
    el.dispatchEvent(new MouseEvent(type, Object.assign({bubbles:true, cancelable:true, view:window, button:0}, init||{})));
  }
  function realClick(el) {
    const r = el.getBoundingClientRect();
    const x = r.x + r.width/2, y = r.y + r.height/2;
    const o = {clientX:x, clientY:y};
    fire(el, "mousedown", o); fire(el, "mouseup", o); fire(el, "click", o);
  }

  const results = [];
  const containers = document.querySelectorAll(".chat-question-carousel-container");
  for (const c of containers) {
    if (!visible(c)) continue;
    const items = Array.from(c.querySelectorAll('.chat-question-list-item[role="option"]'));
    if (items.length === 0) continue;

    // Pick a positive option; never pick a negative one.
    let chosen = null;
    for (const it of items) {
      const lbl = (it.querySelector(".chat-question-list-label")?.innerText || it.innerText || "").trim();
      if (NEGATIVE.test(lbl)) continue;
      if (POSITIVE.test(lbl)) { chosen = it; break; }
    }
    if (!chosen) continue;

    const label = (chosen.querySelector(".chat-question-list-label")?.innerText || "").trim().slice(0, 80);

    // 1) Select the option (real mousedown/mouseup/click).
    if (!chosen.classList.contains("selected")) realClick(chosen);

    // 2) Submit. Prefer an explicit submit button if rendered; otherwise
    //    dispatch Cmd+Enter on the listbox (footer hint says "⌘↵ to submit").
    const submitBtn =
      c.querySelector(".chat-question-submit") ||
      c.querySelector("a.monaco-button:not(.chat-question-close):not(.chat-question-collapse-toggle)");
    let how = null;
    if (submitBtn && visible(submitBtn)) {
      realClick(submitBtn);
      how = "submit-button";
    } else {
      const list = c.querySelector(".chat-question-list") || c;
      const k = {key:"Enter", code:"Enter", keyCode:13, which:13, metaKey:true, bubbles:true, cancelable:true};
      list.dispatchEvent(new KeyboardEvent("keydown", k));
      list.dispatchEvent(new KeyboardEvent("keyup", k));
      how = "cmd-enter";
    }

    results.push({label, how});
  }
  return JSON.stringify({url: location.href, count: results.length, results});
})()
"""


# VS Code Copilot Chat tool-confirmation dialog (variant 2): a small inline
# widget with explicit Allow / Skip buttons (e.g. "Run zsh command?" with a
# code block). Container: `div.chat-confirmation-widget-container` with
# `aria-label` starting "Chat Confirmation Dialog ...". Buttons live inside
# `.chat-confirmation-widget-buttons` as `a.monaco-button` (the negative
# "Skip" carries the extra class `secondary`).
CLICK_CHAT_CONFIRMATION_JS = r"""
(() => {
  const POSITIVE = /^(yes|allow|approve|accept|run|continue|confirm|ok)\b/i;
  const NEGATIVE = /^(no|stop|cancel|deny|reject|skip)\b/i;

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0) return false;
    return true;
  }
  function fire(el, type, init) {
    el.dispatchEvent(new MouseEvent(type, Object.assign({bubbles:true, cancelable:true, view:window, button:0}, init||{})));
  }
  function realClick(el) {
    const r = el.getBoundingClientRect();
    const x = r.x + r.width/2, y = r.y + r.height/2;
    const o = {clientX:x, clientY:y};
    fire(el, "mousedown", o); fire(el, "mouseup", o); fire(el, "click", o);
  }

  const results = [];
  const widgets = document.querySelectorAll(".chat-confirmation-widget-container");
  for (const w of widgets) {
    if (!visible(w)) continue;
    // Candidate buttons: anchors / buttons inside the widget's button row,
    // excluding dropdown chevrons (`.monaco-dropdown` triggers).
    const btnRoot = w.querySelector(".chat-confirmation-widget-buttons") || w;
    const candidates = Array.from(btnRoot.querySelectorAll('a.monaco-button, button.monaco-button, [role="button"].monaco-button'));

    let chosen = null;
    for (const b of candidates) {
      if (!visible(b)) continue;
      // Skip the chevron of a split-button dropdown.
      if (b.classList.contains("monaco-dropdown-button")) continue;
      // The negative button is marked with the `secondary` class in VS Code's
      // monaco button theme — never click it.
      if (b.classList.contains("secondary")) continue;
      const txt = (b.innerText || b.textContent || "").trim();
      const aria = (b.getAttribute("aria-label") || "").trim();
      const label = txt || aria;
      if (NEGATIVE.test(label)) continue;
      if (POSITIVE.test(label)) { chosen = b; break; }
    }
    if (!chosen) continue;

    const label = ((chosen.innerText || chosen.textContent) || chosen.getAttribute("aria-label") || "").trim().slice(0, 80);
    realClick(chosen);
    results.push({label, dialog: (w.getAttribute("aria-label") || "").slice(0, 120)});
  }
  return JSON.stringify({url: location.href, count: results.length, results});
})()
"""


# Sweep across all Cursor chat tabs (rendered as VS Code editor tabs). Inactive
# chat tabs aren't mounted in the DOM, so the only way to click a Run button in
# a non-foreground chat is to activate that tab, scan, click, then restore.
SWEEP_TABS_AND_CLICK_JS = r"""
(async () => {
  const VERBS = ["Run", "Allow", "Approve", "Accept", "Yes"];
  const CLICKABLE_FRAGS = ["monaco-button", "action-label", "anysphere-button", "composer-run-button"];

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
    if (el.hasAttribute && el.hasAttribute("disabled")) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    const cs = el.ownerDocument.defaultView.getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0) return false;
    return true;
  }
  function looksClickable(el) {
    if (!(el instanceof Element)) return false;
    if (el.tagName === "BUTTON") return true;
    if ((el.getAttribute("role") || "") === "button") return true;
    if (el.classList) for (const c of CLICKABLE_FRAGS) if (el.classList.contains(c)) return true;
    return false;
  }
  function clickableAncestor(el) {
    let cur = el;
    for (let i = 0; i < 8 && cur; i++) { if (looksClickable(cur)) return cur; cur = cur.parentElement; }
    return null;
  }
  function textOf(el) { return ((el.innerText || el.textContent) || "").trim(); }

  // VS Code editor tabs activate on mousedown (not click). Use real events
  // bubbling from the tab's center so the workbench's drag handlers see them.
  function activateTab(el) {
    const r = el.getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    const opts = { bubbles: true, cancelable: true, view: window, button: 0, clientX: x, clientY: y };
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
  }
  function describe(el) {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      text: textOf(el).slice(0, 80),
      classes: (el.className && el.className.toString) ? el.className.toString().slice(0, 200) : "",
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    };
  }
  function findApproval() {
    for (const node of document.querySelectorAll("*")) {
      const txt = textOf(node);
      if (!txt || !VERBS.includes(txt)) continue;
      const target = clickableAncestor(node);
      if (!target || !visible(target)) continue;
      return target;
    }
    return null;
  }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const results = [];

  // 1) Try the currently active tab first (cheap path).
  let btn = findApproval();
  if (btn) {
    const d = describe(btn);
    btn.click();
    results.push({ tab: "<active>", clicked: d });
    return JSON.stringify({ clicked: results.length, results });
  }

  // 2) Iterate Cursor chat tabs. Cursor chats are editor tabs that contain a
  //    `.composer-tab-label` descendant; clicking the .tab activates them.
  const allTabs = Array.from(document.querySelectorAll('div.tab[role="tab"]'));
  const chatTabs = allTabs.filter(t => t.querySelector(".composer-tab-label"));
  if (chatTabs.length === 0) {
    return JSON.stringify({ clicked: 0, results: [], note: "no composer chat tabs found" });
  }
  const originallyActive = chatTabs.find(t => t.classList.contains("active")) || allTabs.find(t => t.classList.contains("active"));

  for (const tab of chatTabs) {
    if (tab.classList.contains("active")) continue;  // already scanned above
    const label = (tab.getAttribute("aria-label") || textOf(tab)).slice(0, 80);

    // Snapshot the current composer body so we can detect when it swaps.
    const beforeBar = document.querySelector(".composer-bar");
    const beforeText = beforeBar ? (beforeBar.innerText || "").slice(0, 200) : "";

    activateTab(tab);

    // Wait for the active editor tab to flip AND the composer body content to
    // actually change (React tree re-mount). Cap at ~1.2s.
    let mounted = false;
    for (let i = 0; i < 24; i++) {
      await sleep(50);
      const isActive = tab.classList.contains("active");
      const nowBar = document.querySelector(".composer-bar");
      const nowText = nowBar ? (nowBar.innerText || "").slice(0, 200) : "";
      if (isActive && nowBar && nowText !== beforeText) { mounted = true; break; }
    }
    // Extra settle so any pending Run buttons have time to render.
    await sleep(150);

    btn = findApproval();
    if (btn) {
      const d = describe(btn);
      btn.click();
      results.push({ tab: label, mounted, clicked: d });
    } else {
      results.push({ tab: label, mounted, clicked: null });
    }
  }

  // 3) Restore originally-active tab so we don't disrupt the user.
  if (originallyActive && !originallyActive.classList.contains("active")) {
    try { activateTab(originallyActive); } catch (_) {}
  }

  return JSON.stringify({ clicked: results.filter(r => r.clicked).length, results });
})()
"""

