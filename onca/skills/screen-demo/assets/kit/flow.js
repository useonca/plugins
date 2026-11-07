/* Onca flow runtime: plays a flow (flow.json, timed by flow.py) on a screen rebuilt from the product's source.
 * Every state is derived from the time alone, so the render engine can draw any frame on its own:
 * OncaFlow.seek(t) resets what the steps touch, then replays every step that started by t.
 * OncaFlow.rect(i) is step i's target box in logical pixels, for flow.py's measure pass.
 * A key step shows its label in #onca-keys (when the page has one) for 0.7 s: a keystroke overlay.
 * The cursor and the camera are not drawn here: the polish adds them from clicks.json, as for a recording. */
(() => {
  const D = window.FLOW_DATA;
  const FADE = 0.25;
  const root = document.getElementById("onca-flow") || document.body;
  const all = (sel) => (sel ? Array.from(root.querySelectorAll(sel)) : []);
  const isField = (el) => el.tagName === "INPUT" || el.tagName === "TEXTAREA";
  const touched = new Map();

  function remember(sel, opts) {
    for (const el of all(sel)) {
      const s = touched.get(el) || { cls: el.className, attrs: {} };
      if (opts.text && !isField(el)) s.text = el.textContent;
      if (opts.text && isField(el)) s.value = el.value;
      for (const name of opts.attrs || []) s.attrs[name] = el.getAttribute(name);
      touched.set(el, s);
    }
  }
  function rememberSet(a) {
    remember(a.set, { text: "text" in a, attrs: a.attr ? Object.keys(a.attr) : [] });
  }
  for (const s of D.steps) {
    if (s.kind === "type") remember(s.into, { text: true });
    if (s.kind === "set") rememberSet(s);
    if (s.kind === "click" || s.kind === "tap") remember(s.target, {});
    if (s.then && s.then.set) rememberSet(s.then);
  }
  const keycap = document.getElementById("onca-keys");

  function reset() {
    for (const [el, s] of touched) {
      if (el.className !== s.cls) el.className = s.cls;
      if ("text" in s && el.textContent !== s.text) el.textContent = s.text;
      if ("value" in s) el.value = s.value;
      for (const [name, v] of Object.entries(s.attrs)) {
        if (v === null) el.removeAttribute(name);
        else el.setAttribute(name, v);
      }
    }
  }

  function applySet(a) {
    for (const el of all(a.set)) {
      if ("text" in a) el.textContent = a.text;
      if ("add" in a) el.classList.add(...a.add.split(/\s+/).filter(Boolean));
      if ("remove" in a) el.classList.remove(...a.remove.split(/\s+/).filter(Boolean));
      if (a.attr) {
        for (const [name, v] of Object.entries(a.attr)) {
          if (v === null || v === false) el.removeAttribute(name);
          else el.setAttribute(name, String(v));
        }
      }
    }
  }

  function typeInto(s, t) {
    const n = Math.min(s.type.length, Math.floor((t - s.t) * s.cps + 1e-6) + 1);
    const typing = t < s.end + 0.4;
    for (const el of all(s.into)) {
      const base = touched.get(el);
      if (isField(el)) el.value = (base.value || "") + s.type.slice(0, n);
      else el.textContent = (base.text || "") + s.type.slice(0, n);
      if (typing) el.classList.add("onca-typing");
    }
  }

  function seek(t) {
    reset();
    if (keycap) keycap.classList.remove("on");
    let cur = D.start;
    let prev = null;
    let since = -1;
    const show = (id, at) => {
      if (id === cur) return;
      prev = cur;
      cur = id;
      since = at;
    };
    for (const s of D.steps) {
      if (t < s.t) break;
      if (s.kind === "show") show(s.show, s.t);
      else if (s.kind === "set") applySet(s);
      else if (s.kind === "type") typeInto(s, t);
      else if (s.kind === "click" || s.kind === "tap" || s.kind === "key") {
        if (s.kind === "key" && keycap && t < s.t + 0.7) {
          keycap.textContent = s.key;
          keycap.classList.add("on");
        }
        if (t < s.end) {
          if (s.kind !== "key") all(s.target).forEach((el) => el.classList.add("onca-pressed"));
        } else if (s.then && s.then.show) show(s.then.show, s.end);
        else if (s.then) applySet(s.then);
      }
    }
    const p = since < 0 ? 1 : Math.min(1, (t - since) / FADE);
    for (const el of root.querySelectorAll("[data-screen]")) {
      const id = el.getAttribute("data-screen");
      const on = id === cur || (id === prev && p < 1);
      el.style.visibility = on ? "visible" : "hidden";
      el.style.zIndex = id === cur ? "2" : "1";
      el.style.opacity = id === cur ? String(1 - Math.pow(1 - p, 3)) : "1";
    }
  }

  const HAND = "a[href], button, [role=button], [role=link], summary, label, select, input[type=submit], input[type=checkbox], input[type=radio]";

  function rect(i) {
    const s = D.steps[i];
    const sel = s.kind === "type" ? s.into : s.target;
    const rr = root.getBoundingClientRect();
    const k = rr.width / D.w || 1;
    const els = all(sel).filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
    });
    if (!els.length) return null;
    const r = els[0].getBoundingClientRect();
    const hand = !!els[0].closest(HAND) || getComputedStyle(els[0]).cursor === "pointer";
    return { x: (r.left - rr.left) / k, y: (r.top - rr.top) / k, w: r.width / k, h: r.height / k, hand };
  }

  window.OncaFlow = { seek, rect };
  window.addEventListener("hf-seek", (e) => seek(e.detail.time));
  seek(0);
})();
