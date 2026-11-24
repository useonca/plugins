/* Onca motion kit runtime. Every part is a pure state function of the time since its cue started, so the
 * render engine can draw any frame on its own: no clock, no requestAnimationFrame, no Math.random, no
 * previous frame. seek(t) applies every cue of window.ONCA_CUES (written by kit.py sync); the engine calls it
 * through hf-seek. events(doc) lists the moments that make a sound, the same list kit.py sound places.
 * In Node, require() gives the same object for tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.OncaMotion = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ------------------------------------------------------------ helpers
  const clamp01 = (p) => Math.min(1, Math.max(0, p));
  const lerp = (a, b, p) => a + (b - a) * p;
  const r3 = (v) => Math.round(v * 1000) / 1000;
  const ease = {
    linear: (p) => clamp01(p),
    outCubic: (p) => 1 - Math.pow(1 - clamp01(p), 3),
    outQuart: (p) => 1 - Math.pow(1 - clamp01(p), 4),
    outExpo: (p) => (p >= 1 ? 1 : p <= 0 ? 0 : 1 - Math.pow(2, -10 * p)),
    inCubic: (p) => Math.pow(clamp01(p), 3),
    inOutQuad: (p) => {
      const q = clamp01(p);
      return q < 0.5 ? 2 * q * q : 1 - Math.pow(-2 * q + 2, 2) / 2;
    },
    inQuart: (p) => Math.pow(clamp01(p), 4),
    inOutCubic: (p) => {
      const q = clamp01(p);
      return q < 0.5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2;
    },
    outQuint: (p) => 1 - Math.pow(1 - clamp01(p), 5),
  };

  /* A closed-form damped spring from 0 to 1: damping z (1 never overshoots), freq in Hz. */
  function spring(t, damping = 0.7, freq = 3) {
    if (t <= 0) return 0;
    const z = damping;
    const w = 2 * Math.PI * freq;
    if (z >= 1) return 1 - Math.exp(-w * t) * (1 + w * t);
    const wd = w * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z / Math.sqrt(1 - z * z)) * Math.sin(wd * t));
  }

  const progress = (t, at, dur) => (dur <= 0 ? (t >= at ? 1 : 0) : clamp01((t - at) / dur));

  /* mulberry32 of (seed, i): the same number for the same pair, in [0, 1). */
  function rand(seed, i) {
    let a = (Math.imul(seed | 0, 0x9e3779b1) + Math.imul((i | 0) + 1, 0x85ebca6b)) | 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /* A torn-paper edge: a CSS polygon() around a w x h box, rough px deep, the same for the same seed. */
  function tornPath(seed, w, h, rough = 6) {
    const pts = [];
    let k = 0;
    const jag = () => rand(seed, k++) * rough;
    const step = Math.max(8, rough * 2);
    for (let x = 0; x < w; x += step) pts.push([x, jag()]);
    pts.push([w, jag()]);
    for (let y = step; y < h; y += step * 2) pts.push([w - jag() * 0.5, y]);
    for (let x = w; x > 0; x -= step) pts.push([x, h - jag()]);
    pts.push([0, h - jag()]);
    for (let y = h - step; y > 0; y -= step * 2) pts.push([jag() * 0.5, y]);
    return "polygon(" + pts.map(([x, y]) => `${x.toFixed(1)}px ${y.toFixed(1)}px`).join(", ") + ")";
  }

  const BASE = { opacity: 1, x: 0, y: 0, scale: 1, rotate: 0, blur: 0 };
  const base = (over) => Object.assign({}, BASE, over || {});
  function transform(b, extra) {
    return `translate(${r3(b.x)}px, ${r3(b.y)}px) rotate(${r3(b.rotate)}deg) scale(${r3(b.scale)})` + (extra || "");
  }
  function applyBase(el, b, extraFilter) {
    el.style.opacity = String(r3(b.opacity));
    el.style.transform = transform(b);
    const blur = b.blur > 0.01 ? `blur(${r3(b.blur)}px)` : "";
    el.style.filter = [blur, extraFilter || ""].filter(Boolean).join(" ") || "none";
  }
  function hexMix(a, b, p) {
    const ok = (c) => typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c);
    if (!ok(a) || !ok(b)) return p < 0.5 ? a : b;
    const ch = (c, i) => parseInt(c.slice(1 + 2 * i, 3 + 2 * i), 16);
    return "#" + [0, 1, 2].map((i) => Math.round(lerp(ch(a, i), ch(b, i), p)).toString(16).padStart(2, "0")).join("");
  }
  const once = (el, key, build) => {
    if (el.getAttribute("data-om-built") !== key) {
      build();
      el.setAttribute("data-om-built", key);
    }
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const ids = (v) => (Array.isArray(v) ? v : v ? [v] : []);

  // ------------------------------------------------------------ the parts
  const parts = {};
  const DUR_DEFAULT = { odometer: 1.4, drop: 0.28, move: 0.6, focus: 0.6 };

  /* Headline word by word: ink (grey to ink), blur, rise or pop. */
  const WORD_IN = { ink: 0.2, blur: 0.13, rise: 0.35, pop: 0.5 };
  function wordList(params) {
    if (Array.isArray(params.words) && params.words.length) return params.words.map((w) => w.text);
    return String(params.text || "").split(/\s+/).filter(Boolean);
  }
  function wordStart(params, i) {
    const w = params.words && params.words[i];
    return w && typeof w.start === "number" ? w.start : i * params.gap;
  }
  parts.words = {
    defaults: { mode: "ink", gap: 0.08, accent: [], from_voice: false },
    dur: (p) => wordStart(p, Math.max(0, wordList(p).length - 1)) + 0.4,
    state(params, t) {
      const n = wordList(params).length;
      const words = [];
      for (let i = 0; i < n; i++) {
        const p = progress(t, wordStart(params, i), WORD_IN[params.mode] || 0.2);
        const s = { opacity: 1, blur: 0, y: 0, scale: 1, ink: 1 };
        if (params.mode === "ink") {
          s.opacity = t >= 0 ? 1 : 0;
          s.ink = ease.outCubic(p);
        } else if (params.mode === "blur") {
          s.opacity = p;
          s.blur = 6 * (1 - p);
        } else if (params.mode === "rise") {
          s.opacity = ease.outCubic(p);
          s.y = 28 * (1 - ease.outExpo(p));
          s.blur = 4 * (1 - p);
        } else {
          const u = t - wordStart(params, i);
          s.opacity = clamp01(u / 0.08);
          s.scale = u <= 0 ? 0.6 : 0.6 + 0.4 * spring(u, 0.55, 3.4);
        }
        words.push(s);
      }
      return { words };
    },
    prepare(el, params) {
      if (params.text || (Array.isArray(params.words) && params.words.length)) return params;
      if (!el.hasAttribute("data-om-text")) el.setAttribute("data-om-text", el.textContent.trim());
      return Object.assign({}, params, { text: el.getAttribute("data-om-text") });
    },
    apply(el, st, params) {
      const list = wordList(params);
      once(el, "words:" + list.join(" "), () => {
        el.innerHTML = list.map((w) => `<span class="om-w">${esc(w)}</span>`).join(" ");
      });
      const spans = el.querySelectorAll(".om-w");
      const accent = new Set(params.accent || []);
      st.words.forEach((s, i) => {
        const sp = spans[i];
        if (!sp) return;
        sp.style.opacity = String(r3(s.opacity));
        sp.style.transform = `translateY(${r3(s.y)}px) scale(${r3(s.scale)})`;
        sp.style.filter = s.blur > 0.01 ? `blur(${r3(s.blur)}px)` : "none";
        if (params.mode === "ink") {
          const on = accent.has(i) ? "var(--om-accent)" : "var(--om-ink)";
          sp.style.color = `color-mix(in srgb, ${on} ${r3(s.ink * 100)}%, var(--om-muted))`;
        } else if (accent.has(i)) sp.style.color = "var(--om-accent)";
      });
    },
  };

  /* An accent box (with corner handles), an ellipse drawn round, or a marker swipe.
   * On an empty element the element is the mark. On an element with content (text, a card, a picture) the part
   * leaves the element alone and draws the mark as its own child over the same area, so the content stays visible. */
  const hasContent = (el) => ((el.textContent || "").trim() !== "") || (el.children && el.children.length > 0) || /^(img|video|canvas|picture|svg)$/i.test(el.tagName || "");
  function markOf(el, params) {
    let host = el.getAttribute("data-om-host");
    if (host === null) {
      host = hasContent(el) ? "1" : "0";
      el.setAttribute("data-om-host", host);
    }
    if (host !== "1") return el;
    let mark = el.querySelector(".om-mark");
    if (!mark) {
      mark = (el.ownerDocument || document).createElement("i");
      mark.className = "om-mark";
      el.appendChild(mark);
      if (typeof getComputedStyle === "function" && getComputedStyle(el).position === "static") el.style.position = "relative";
    }
    mark.style.inset = -params.pad + "px";
    return mark;
  }
  parts.highlight = {
    defaults: { style: "box", pad: 12, draw: 0.35, handles: true },
    dur: (p) => p.draw + 0.6,
    state(params, t) {
      const draw = ease.outCubic(progress(t, 0, params.draw));
      const handles = [0, 1, 2, 3].map((i) =>
        params.handles && params.style === "box" ? r3(spring(t - params.draw - i * 0.04, 0.55, 4)) : 0
      );
      return { draw, opacity: t >= 0 ? 1 : 0, handles };
    },
    apply(el, st, params) {
      const mark = markOf(el, params);
      once(mark, "highlight:" + params.style, () => {
        mark.classList.add("om-highlight");
        mark.setAttribute("data-style", params.style);
        mark.setAttribute("data-layout-allow-occlusion", "");  // it sits over its words on purpose
        if (params.style === "ellipse") {
          mark.innerHTML = '<svg viewBox="0 0 100 100" preserveAspectRatio="none"><ellipse cx="50" cy="50" rx="48" ry="44"/></svg>';
        } else if (params.style === "box" && params.handles) {
          mark.innerHTML = '<i class="om-handle"></i><i class="om-handle"></i><i class="om-handle"></i><i class="om-handle"></i>';
        }
      });
      mark.style.opacity = String(st.opacity);
      mark.style.setProperty("--om-pad", params.pad + "px");
      if (params.style === "ellipse") {
        const mask = `conic-gradient(from -100deg, #000 ${r3(st.draw * 360)}deg, transparent 0)`;
        mark.style.webkitMaskImage = mask;
        mark.style.maskImage = mask;
        mark.style.clipPath = "none";
      } else {
        mark.style.clipPath = `inset(0 ${r3((1 - st.draw) * 100)}% 0 0)`;
      }
      mark.querySelectorAll(".om-handle").forEach((h, i) => (h.style.transform = `scale(${st.handles[i]})`));
    },
  };

  /* Word captions on the voice, a few words at a time, the spoken word lit. */
  function chunkList(params) {
    return Array.isArray(params.chunks) ? params.chunks : [];
  }
  const KEY_DRAW = 0.35;
  /* The index of the board beat playing at t (-1 before the first break). */
  function beatAt(params, t) {
    let k = -1;
    (Array.isArray(params.breaks) ? params.breaks : []).forEach((b, i) => {
      if (t >= b - 1e-9) k = i;
    });
    return k;
  }
  /* The tone (light or dark) of the beat playing at t, so the captions stay readable on every scene. */
  const toneAt = (params, t) => (Array.isArray(params.tones) && params.tones[Math.max(0, beatAt(params, t))]) || "light";
  /* Whether the captions step aside at t (a headline beat says the line in big type itself). */
  const hiddenAt = (params, t) => beatAt(params, t) >= 0 && Array.isArray(params.hide) && !!params.hide[beatAt(params, t)];
  parts.captions = {
    defaults: { max_words: 4, style: "box", from_voice: true, position: "top", dim: 0.35 },
    dur: (p) => {
      const c = chunkList(p);
      return c.length ? c[c.length - 1][c[c.length - 1].length - 1].end + 0.25 : 1;
    },
    state(params, t) {
      const chunks = chunkList(params);
      let chunk = -1;
      for (let i = 0; i < chunks.length; i++) {
        const start = chunks[i][0].start;
        const next = i + 1 < chunks.length ? chunks[i + 1][0].start : Infinity;
        const hold = params.style === "reel" ? Infinity : 0.25;  // a reel caption stays up until the next phrase
        const end = Math.min(next, chunks[i][chunks[i].length - 1].end + hold);
        if (t >= start && t < end) chunk = i;
      }
      if (chunk < 0 || hiddenAt(params, t)) return { chunk: -1, text: "", active: -1, key: -1, key_draw: 0, handles: [0, 0, 0, 0], tone: toneAt(params, t) };
      const words = chunks[chunk];
      let active = -1;
      let key = -1;
      words.forEach((w, i) => {
        if (t >= w.start) active = i;
        if (w.key && key < 0) key = i;
      });
      const since = key >= 0 ? t - words[key].start : -1;
      const keyDraw = key >= 0 ? r3(ease.outCubic(progress(since, 0, KEY_DRAW))) : 0;
      const handles = [0, 1, 2, 3].map((i) => (key >= 0 ? r3(Math.max(0, spring(since - KEY_DRAW - i * 0.04, 0.55, 4))) : 0));
      return { chunk, text: words.map((w) => w.text).join(" "), active, key, key_draw: keyDraw, handles, tone: toneAt(params, t) };
    },
    apply(el, st, params) {
      const reel = params.style === "reel";
      el.classList.add("om-caption");
      el.setAttribute("data-style", params.style);
      if (reel) {
        el.setAttribute("data-position", params.position);
        el.setAttribute("data-tone", st.tone);
      }
      el.setAttribute("data-motion-blur", "off");  // a whip behind the captions must not smear them
      const words = st.chunk >= 0 ? chunkList(params)[st.chunk] : [];
      once(el, "captions:" + st.chunk, () => {
        el.innerHTML = words.map((w, i) => {
          if (!reel || i !== st.key) return `<span class="om-cw">${esc(w.text)}</span>`;
          const box = '<i class="om-keybox om-highlight" data-style="box">' + '<i class="om-handle"></i>'.repeat(4) + "</i>";
          const emoji = w.emoji ? ` <span class="om-emoji">${esc(w.emoji)}</span>` : "";
          return `<span class="om-cw om-key">${box}${esc(w.text)}</span>${emoji}`;
        }).join(" ");
      });
      el.style.opacity = st.chunk >= 0 ? "1" : "0";
      if (reel) el.style.setProperty("--om-dim", String(params.dim));
      el.querySelectorAll(".om-cw").forEach((s, i) => {
        if (reel) {
          s.classList.toggle("om-dim", i > st.active);
          s.classList.toggle("om-on", i <= st.active);
        } else s.classList.toggle("om-on", i === st.active);
      });
      const box = el.querySelectorAll(".om-keybox")[0];
      if (box) {
        box.style.clipPath = `inset(-20px ${r3((1 - st.key_draw) * 100)}% -20px -20px)`;
        box.style.opacity = st.key_draw > 0 ? "1" : "0";
        box.querySelectorAll(".om-handle").forEach((h, i) => (h.style.transform = `scale(${st.handles[i]})`));
      }
    },
  };

  /* A rolling counter: each digit column rolls from its start digit to its end digit, right to left. */
  function formatNumber(v, format) {
    const s = String(Math.round(Math.abs(v)));
    const body = format === "comma" ? s.replace(/\B(?=(\d{3})+(?!\d))/g, ",") : s;
    return (v < 0 ? "-" : "") + body;
  }
  parts.odometer = {
    defaults: { from: 0, format: "comma", prefix: "", suffix: "", tiles: false, stagger: 0.05 },
    dur: () => DUR_DEFAULT.odometer,
    state(params, t, dur) {
      const to = Number(params.to);
      const from = Number(params.from);
      const target = formatNumber(to, params.format);
      const digits = target.replace(/\D/g, "").length;
      const fromDigits = String(Math.round(Math.abs(from))).padStart(digits, "0").slice(-digits);
      const n = digits;
      const roll = Math.max(0.1, dur - (n - 1) * params.stagger);
      const columns = [];
      let d = 0;
      for (const ch of target) {
        if (!/\d/.test(ch)) {
          columns.push({ char: ch, value: null });
          continue;
        }
        const fromRight = n - 1 - d;
        const p = ease.outCubic(progress(t, fromRight * params.stagger, roll));
        columns.push({ char: ch, value: r3(lerp(Number(fromDigits[d]), Number(ch), p)) });
        d++;
      }
      const v = lerp(from, to, ease.outCubic(progress(t, 0, dur)));
      return { text: params.prefix + formatNumber(v, params.format) + params.suffix, columns };
    },
    apply(el, st, params) {
      once(el, "odometer:" + st.columns.map((c) => c.char).join(""), () => {
        el.classList.add("om-odometer");
        el.classList.toggle("om-tiles", !!params.tiles);
        const strip = '<span class="om-strip">' + "0123456789".split("").map((c) => `<b>${c}</b>`).join("") + "</span>";
        el.innerHTML =
          (params.prefix ? `<span class="om-fix">${esc(params.prefix)}</span>` : "") +
          st.columns.map((c) => (c.value === null ? `<span class="om-sep">${esc(c.char)}</span>` : `<span class="om-col">${strip}</span>`)).join("") +
          (params.suffix ? `<span class="om-fix">${esc(params.suffix)}</span>` : "");
      });
      el.setAttribute("aria-label", st.text);
      const cols = el.querySelectorAll(".om-col .om-strip");
      let k = 0;
      for (const c of st.columns) {
        if (c.value === null) continue;
        if (cols[k]) {
          cols[k].style.transform = `translateY(${r3(-c.value)}em)`;
          // only the digits in the window are drawn, so nothing hidden behind the clip counts as text
          cols[k].querySelectorAll("b").forEach((b, d) => (b.style.visibility = Math.abs(d - c.value) < 1 ? "visible" : "hidden"));
        }
        k++;
      }
    },
  };

  /* A 3D tilted grid of cards with a wave running through it from one card. */
  parts["card-grid"] = {
    defaults: { rows: 6, cols: 5, tilt: 55, wave_from: [0, 0], wave_speed: 8, lift: 40 },
    dur: (p) => Math.hypot(p.rows, p.cols) / p.wave_speed + 0.8,
    state(params, t) {
      const cards = [];
      const [r0, c0] = params.wave_from;
      for (let r = 0; r < params.rows; r++) {
        for (let c = 0; c < params.cols; c++) {
          const u = t - Math.hypot(r - r0, c - c0) / params.wave_speed;
          const bump = u <= 0 ? 0 : Math.sin(Math.PI * clamp01(u / 0.6));
          cards.push({ z: r3(params.lift * bump), rotateX: r3(-12 * bump), tint: r3(bump) });
        }
      }
      return { cards };
    },
    apply(el, st, params) {
      once(el, "grid:" + params.rows + "x" + params.cols, () => {
        el.classList.add("om-grid");
        el.style.setProperty("--om-cols", String(params.cols));
        const need = params.rows * params.cols - el.querySelectorAll(":scope > .om-card").length;
        for (let i = 0; i < need; i++) {
          const card = el.ownerDocument.createElement("div");
          card.className = "om-card";
          el.appendChild(card);
        }
      });
      el.style.transform = `perspective(1400px) rotateX(${params.tilt}deg) rotateZ(-8deg)`;
      el.querySelectorAll(":scope > .om-card").forEach((card, i) => {
        const s = st.cards[i];
        if (!s) return;
        card.style.transform = `translateZ(${s.z}px) rotateX(${s.rotateX}deg)`;
        card.style.setProperty("--om-tint", String(s.tint));
      });
    },
  };

  /* A pop-in at a tilt, on a spring; with `each`, every matching child in turn. */
  parts.pop = {
    defaults: { from_scale: 0.6, rotate: 0, rotate_from: -8, damping: 0.6, freq: 3.2, each: "", stagger: 0.06, origin: "center" },
    dur: (p) => (p.each ? (Math.max(1, p.count || 1) - 1) * p.stagger : 0) + 0.8,
    state(params, t) {
      const n = params.each ? Math.max(0, params.count || 0) : 1;
      const items = [];
      for (let i = 0; i < n; i++) {
        const u = t - i * params.stagger;
        const s = spring(u, params.damping, params.freq);
        items.push(base({
          opacity: clamp01(u / 0.08),
          scale: r3(lerp(params.from_scale, 1, s)),
          rotate: r3(lerp(params.rotate_from, params.rotate, s)),
        }));
      }
      return { items };
    },
    apply(el, st, params) {
      const targets = params.each ? el.querySelectorAll(params.each) : [el];
      st.items.forEach((b, i) => {
        if (!targets[i]) return;
        targets[i].style.transformOrigin = params.origin;
        applyBase(targets[i], b);
      });
    },
    prepare(el, params) {
      return params.each ? Object.assign({}, params, { count: el.querySelectorAll(params.each).length }) : params;
    },
  };

  /* A label, pin, clip or tape slapped on: falls from a little large and lands with its shadow. */
  parts.drop = {
    defaults: { from_scale: 1.25, rotate: 0 },
    dur: () => DUR_DEFAULT.drop,
    state(params, t, dur) {
      const e = ease.inCubic(progress(t, 0, dur));
      const settle = t > dur ? 0.03 * Math.exp(-(t - dur) * 18) * Math.sin((t - dur) * 40) : 0;
      return Object.assign(base({ opacity: clamp01((t / dur) * 3), scale: r3(lerp(params.from_scale, 1, e) - settle), rotate: params.rotate }), { shadow: r3(e) });
    },
    apply(el, st) {
      const s = st.shadow;
      applyBase(el, st, `drop-shadow(0 ${r3(2 + 14 * (1 - s))}px ${r3(3 + 18 * (1 - s))}px rgba(0,0,0,${r3(0.32 - 0.14 * (1 - s))}))`);
    },
  };

  /* A slide, stack or whip from one Base to another on an ease. */
  parts.move = {
    defaults: { from: {}, to: {}, ease: "outExpo" },
    dur: () => DUR_DEFAULT.move,
    state(params, t, dur) {
      const e = (ease[params.ease] || ease.outExpo)(progress(t, 0, dur));
      const a = base(params.from);
      const b = base(params.to);
      const out = {};
      for (const k of Object.keys(BASE)) out[k] = r3(lerp(a[k], b[k], e));
      for (const k of ["w", "h"]) {  // a box change (width and height in px), as the presenter moves place
        const from = params.from || {};
        const to = params.to || {};
        if (k in from || k in to) out[k] = r3(lerp(k in from ? from[k] : to[k], k in to ? to[k] : from[k], e));
      }
      return out;
    },
    apply(el, st) {
      applyBase(el, st);
      if (st.w != null) el.style.width = st.w + "px";
      if (st.h != null) el.style.height = st.h + "px";
    },
  };

  /* A line or bars drawing in, then its label. */
  parts.chart = {
    defaults: { kind: "line", values: [], label: "", draw: 1.0 },
    dur: (p) => p.draw + 0.4,
    state(params, t) {
      const vals = params.values.map(Number);
      const max = Math.max(1e-9, ...vals);
      const draw = ease.outCubic(progress(t, 0, params.draw));
      let dot = { x: 0, y: 0 };
      if (vals.length) {
        const f = draw * (vals.length - 1);
        const i = Math.min(vals.length - 2, Math.floor(f));
        const v = vals.length === 1 ? vals[0] : lerp(vals[Math.max(0, i)], vals[Math.max(0, i) + 1], f - Math.max(0, i));
        dot = { x: r3(vals.length === 1 ? 0 : f / (vals.length - 1)), y: r3(v / max) };
      }
      const bars = vals.map((v, i) => r3((v / max) * ease.outExpo(progress(t, i * 0.06, params.draw))));
      const lp = ease.outCubic(progress(t, params.draw, 0.3));
      return { draw: r3(draw), dot, bars, label: base({ opacity: r3(lp), y: r3(12 * (1 - lp)) }) };
    },
    apply(el, st, params) {
      const vals = params.values.map(Number);
      const max = Math.max(1e-9, ...vals);
      once(el, "chart:" + params.kind + ":" + vals.join(","), () => {
        el.classList.add("om-chart");
        el.setAttribute("data-kind", params.kind);
        const pts = vals.map((v, i) => `${vals.length === 1 ? 0 : (i / (vals.length - 1)) * 100},${100 - (v / max) * 100}`).join(" ");
        const label = params.label ? `<div class="om-chart-label">${esc(params.label)}</div>` : "";
        el.innerHTML =
          params.kind === "bars"
            ? `<div class="om-bars">${vals.map(() => '<i class="om-bar"></i>').join("")}</div>${label}`
            : `<svg viewBox="0 0 100 100" preserveAspectRatio="none"><polyline points="${pts}"/></svg><i class="om-dot"></i>${label}`;
      });
      const svg = el.querySelector("svg");
      if (svg) svg.style.clipPath = `inset(-20px ${r3((1 - st.dot.x) * 100)}% -20px -20px)`;
      const dot = el.querySelector(".om-dot");
      if (dot) {
        dot.style.left = `${r3(st.dot.x * 100)}%`;
        dot.style.top = `${r3(100 - st.dot.y * 100)}%`;
        dot.style.opacity = st.draw > 0 ? "1" : "0";
      }
      el.querySelectorAll(".om-bar").forEach((b, i) => (b.style.transform = `scaleY(${st.bars[i]})`));
      const lab = el.querySelector(".om-chart-label");
      if (lab) applyBase(lab, st.label);
    },
  };

  /* A focus pull: blur to sharp (in) or sharp to blur (out), with a slight settle in scale. */
  parts.focus = {
    defaults: { from_blur: 18, from_scale: 1.06, direction: "in" },
    dur: () => DUR_DEFAULT.focus,
    state(params, t, dur) {
      let p = ease.outCubic(progress(t, 0, dur));
      if (params.direction === "out") p = 1 - ease.inCubic(progress(t, 0, dur));
      return base({ blur: r3(params.from_blur * (1 - p)), scale: r3(lerp(params.from_scale, 1, p)) });
    },
    apply(el, st) {
      applyBase(el, st);
    },
  };

  /* A dark stage lit by a cone from above, which may flip to a light stage (or the other way). */
  parts.spotlight = {
    defaults: { mode: "dark", cone_x: 0.5, cone_w: 0.5, flip_at: null },
    dur: (p) => (p.flip_at == null ? 1.2 : p.flip_at + 0.6),
    state(params, t) {
      const light = r3(ease.outCubic(progress(t, 0, 0.8)));
      const flip = params.flip_at == null ? 0 : r3(ease.inOutQuad(progress(t, params.flip_at, 0.4)));
      return { light, flip };
    },
    apply(el, st, params) {
      el.classList.add("om-spotlight");
      const dark = params.mode === "dark";
      const paperShare = r3((dark ? st.flip : 1 - st.flip) * 100);
      const ground = `color-mix(in srgb, var(--om-paper) ${paperShare}%, var(--om-ink))`;
      const coneAlpha = r3(0.22 * st.light * (1 - paperShare / 100));
      el.style.background =
        `radial-gradient(ellipse ${r3(params.cone_w * 100)}% 95% at ${r3(params.cone_x * 100)}% -8%, ` +
        `rgba(255,255,255,${coneAlpha}) 0%, rgba(255,255,255,0) 72%), ${ground}`;
    },
  };

  /* A chat bubble: typing dots, then the message, with a small pop as it lands. */
  parts.bubble = {
    defaults: { side: "in", text: "", typing: 0.9 },
    dur: (p) => p.typing + 0.6,
    state(params, t) {
      const text = String(params.text || "");
      const land = t - params.typing;
      const grow = spring(t, 0.6, 4);
      const scale = t <= 0 ? 0 : land < 0 ? grow : grow * (0.94 + 0.06 * spring(land, 0.5, 5));
      const dotsOn = t >= 0 && land < 0 ? 1 : 0;
      const dots = [0, 1, 2].map((i) => r3(dotsOn ? -4 * Math.max(0, Math.sin(2 * Math.PI * 1.6 * t - i * 0.9)) : 0));
      const chars = land >= 0 ? text.length : 0;
      const charY = [];
      for (let i = 0; i < chars; i++) charY.push(r3(6 * (1 - ease.outCubic(progress(land, i * 0.012, 0.25)))));
      return { scale: r3(scale), dots, dots_on: dotsOn, chars, char_y: charY };
    },
    apply(el, st, params) {
      const text = String(params.text || "");
      once(el, "bubble:" + params.side + ":" + text, () => {
        el.classList.add("om-bubble");
        el.setAttribute("data-side", params.side);
        el.innerHTML =
          '<span class="om-dots"><i></i><i></i><i></i></span><span class="om-text">' +
          Array.from(text).map((c) => `<span>${c === " " ? " " : esc(c)}</span>`).join("") +
          "</span>";
      });
      el.style.transform = `scale(${st.scale})`;
      el.style.opacity = st.scale > 0 ? "1" : "0";
      const dots = el.querySelector(".om-dots");
      dots.style.display = st.dots_on ? "inline-flex" : "none";
      dots.querySelectorAll("i").forEach((d, i) => (d.style.transform = `translateY(${st.dots[i]}px)`));
      const textEl = el.querySelector(".om-text");
      textEl.style.display = st.chars > 0 ? "inline" : "none";
      textEl.querySelectorAll("span").forEach((s, i) => {
        s.style.opacity = i < st.chars ? "1" : "0";
        s.style.transform = `translateY(${st.char_y[i] || 0}px)`;
      });
    },
  };

  /* One shape into the next: size, corner radius and colour move together with a stretch and a blur at the
   * fastest moment; each state's own content fades in as the last one's fades out. */
  parts.morph = {
    defaults: { states: [], dur: 0.35, stretch: 0.12, blur: 12 },
    dur: (p) => (p.states.length ? p.states[p.states.length - 1].at + p.dur : 1),
    state(params, t) {
      const S = params.states;
      let k = 0;
      for (let i = 0; i < S.length; i++) if (t >= S[i].at) k = i;
      const cur = S[k];
      const prev = k > 0 ? S[k - 1] : cur;
      const p = k > 0 ? progress(t, cur.at, params.dur) : 1;
      const e = ease.outCubic(p);
      const bump = k > 0 && p < 1 ? Math.sin(Math.PI * p) : 0;
      const num = (key, dflt) => r3(lerp(prev[key] == null ? dflt : prev[key], cur[key] == null ? dflt : cur[key], e));
      const all = [];
      S.forEach((s) => ids(s.show).forEach((id) => all.indexOf(id) < 0 && all.push(id)));
      const show = all.map((id) => {
        let opacity = 0;
        if (ids(cur.show).indexOf(id) >= 0) opacity = k > 0 && ids(prev.show).indexOf(id) < 0 ? progress(t, cur.at + params.dur * 0.3, params.dur * 0.7) : 1;
        else if (k > 0 && ids(prev.show).indexOf(id) >= 0) opacity = 1 - progress(t, cur.at, params.dur * 0.4);
        return { id, opacity: r3(opacity), blur: r3(8 * (1 - opacity)) };
      });
      return {
        w: num("w", 100), h: num("h", 100), radius: num("radius", 0),
        bg: hexMix(prev.bg || cur.bg || "#FFFFFF", cur.bg || prev.bg || "#FFFFFF", e),
        stretch: r3(params.stretch * bump), blur: r3(params.blur * bump), show,
      };
    },
    apply(el, st) {
      el.classList.add("om-morph");
      el.style.width = st.w + "px";
      el.style.height = st.h + "px";
      el.style.borderRadius = st.radius + "px";
      el.style.background = st.bg;
      el.style.transform = `scale(${r3(1 + st.stretch)}, ${r3(1 - st.stretch * 0.5)})`;
      el.style.filter = st.blur > 0.01 ? `blur(${st.blur}px)` : "none";
      const doc = el.ownerDocument;
      st.show.forEach((s) => {
        const c = doc.getElementById(s.id);
        if (!c) return;
        c.style.opacity = String(s.opacity);
        c.style.filter = s.blur > 0.01 ? `blur(${s.blur}px)` : "none";
      });
    },
  };

  /* An SVG drawn on stroke by stroke (every path, line, polyline, circle, rect and ellipse inside, in page
   * order, measured as pathLength 1), then its fills fade in. */
  const DRAWN = "path, line, polyline, polygon, circle, rect, ellipse";
  const FILL_IN = 0.3;
  parts.draw = {
    defaults: { stagger: 0.08, draw: 0.6, fill_after: true, ease: "outCubic", count: 1 },
    dur: (p) => Math.max(0, (p.count || 1) - 1) * p.stagger + p.draw + (p.fill_after ? FILL_IN : 0),
    state(params, t) {
      const n = Math.max(1, params.count || 1);
      const e = ease[params.ease] || ease.outCubic;
      const offsets = [];
      for (let i = 0; i < n; i++) offsets.push(r3(1 - e(progress(t, i * params.stagger, params.draw))));
      const fill = params.fill_after ? r3(ease.outCubic(progress(t, (n - 1) * params.stagger + params.draw, FILL_IN))) : 1;
      return { offsets, fill };
    },
    prepare(el, params) {
      return Object.assign({}, params, { count: Math.max(1, el.querySelectorAll(DRAWN).length) });
    },
    apply(el, st) {
      el.querySelectorAll(DRAWN).forEach((p, i) => {
        p.setAttribute("pathLength", "1");
        p.style.strokeDasharray = "1 1";
        p.style.strokeDashoffset = String(st.offsets[Math.min(i, st.offsets.length - 1)]);
        p.style.fillOpacity = String(st.fill);
      });
    },
  };

  /* A card tilting into 3D perspective as it arrives (context cards only: the hero product UI stays flat). */
  parts.tilt = {
    defaults: { rx: 12, ry: -18, from_rx: 0, from_ry: 0, z: 0, perspective: 1400, ease: "outCubic", from_scale: 0.96, fade: true },
    dur: () => 0.8,
    state(params, t, dur) {
      const e = (ease[params.ease] || ease.outCubic)(progress(t, 0, dur));
      return { rx: r3(lerp(params.from_rx, params.rx, e)), ry: r3(lerp(params.from_ry, params.ry, e)), z: params.z,
               perspective: params.perspective, scale: r3(lerp(params.from_scale, 1, e)),
               opacity: params.fade ? r3(clamp01(t / 0.15)) : 1 };
    },
    apply(el, st) {
      el.style.opacity = String(st.opacity);
      el.style.transform = `perspective(${st.perspective}px) rotateX(${st.rx}deg) rotateY(${st.ry}deg) translateZ(${st.z}px) scale(${st.scale})`;
    },
  };

  /* Text typed in at cps characters a second, with a caret that blinks once the line is done. */
  function typedText(params) {
    return String(params.text || "");
  }
  parts.type = {
    defaults: { text: "", cps: 28, caret: true },
    dur: (p) => typedText(p).length / Math.max(1, p.cps),
    state(params, t, dur) {
      const text = typedText(params);
      const chars = Math.max(0, Math.min(text.length, Math.floor(t * params.cps + 1e-9)));
      const caret = params.caret && t >= 0 && (t < dur || Math.floor((t - dur) / 0.5) % 2 === 0);
      return { chars, caret: !!caret };
    },
    prepare(el, params) {
      if (params.text) return params;
      if (!el.hasAttribute("data-om-text")) el.setAttribute("data-om-text", el.textContent.trim());
      return Object.assign({}, params, { text: el.getAttribute("data-om-text") });
    },
    apply(el, st, params) {
      const shown = typedText(params).slice(0, st.chars);
      once(el, "type:" + shown + ":" + st.caret, () => {
        el.innerHTML = esc(shown) + (st.caret ? '<i class="om-caret"></i>' : "");
      });
    },
  };

  /* The slow camera push that keeps a beat moving: scale and drift from one place to another over the beat. */
  const DRIFT_FROM = { scale: 1, x: 0, y: 0 };
  const DRIFT_TO = { scale: 1.05, x: 0, y: 0 };
  parts.drift = {
    defaults: { from: DRIFT_FROM, to: DRIFT_TO, ease: "inOutQuad" },
    dur: () => 2.5,
    state(params, t, dur) {
      const e = (ease[params.ease] || ease.inOutQuad)(progress(t, 0, dur));
      const a = Object.assign({}, DRIFT_FROM, params.from);
      const b = Object.assign({}, DRIFT_TO, params.to);
      return { scale: r3(lerp(a.scale, b.scale, e)), x: r3(lerp(a.x, b.x, e)), y: r3(lerp(a.y, b.y, e)) };
    },
    apply(el, st) {
      el.style.transform = `translate(${st.x}px, ${st.y}px) scale(${st.scale})`;
    },
  };

  /* A scene change on the incoming scene (a full-frame element above the outgoing one): a hard cut, a paper
   * slide, a fast whip (the engine's motion blur smears it) or a tear that reveals it behind a torn edge; with
   * `out`, the outgoing scene is hidden once the change is over. */
  const SCENE_DUR = { cut: 0.04, slide: 0.6, whip: 0.35, tear: 0.55, focus: 0.35, zoom: 0.35, fade: 0.3 };
  const FOCUS_OUT = 0.18;  // the outgoing scene blurs away over this
  const FOCUS_IN = 0.2;  // the incoming one sharpens over the change's last this
  const NEUTRAL_OUT = { opacity: 1, blur: 0, scale: 1 };
  /* The camera-like changes: focus pull, zoom-through, fade (in: the incoming scene; out: the outgoing one). */
  function cameraChange(kind, t, dur) {
    const shown = t >= 0;
    if (kind === "focus") {
      const q = ease.outCubic(progress(t, 0, FOCUS_OUT));
      const start = dur - FOCUS_IN;
      const p = ease.outCubic(progress(t, start, FOCUS_IN));
      return { in: { opacity: t >= start - 1e-9 ? r3(Math.max(p, 0.001)) : 0, blur: r3(10 * (1 - p)), scale: r3(lerp(0.97, 1, p)) },
               out: shown ? { opacity: r3(1 - q), blur: r3(10 * q), scale: r3(lerp(1, 1.03, q)) } : null };
    }
    if (kind === "zoom") {
      const q = ease.inQuart(progress(t, 0, dur));
      const p = ease.outExpo(progress(t, 0, dur));
      return { in: { opacity: shown ? r3(ease.outCubic(progress(t, 0, dur * 0.6))) : 0, blur: 0, scale: r3(lerp(0.9, 1, p)) },
               out: shown ? { opacity: r3(1 - q), blur: 0, scale: r3(lerp(1, 2.5, q)) } : null };
    }
    return { in: { opacity: shown ? r3(progress(t, 0, dur)) : 0, blur: 0, scale: 1 }, out: null };  // fade
  }
  const SCENE_DIR = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] };
  parts.scene = {
    defaults: { kind: "slide", from: "right", out: null, seed: 3 },
    dur: (p) => SCENE_DUR[p.kind] || 0.6,
    state(params, t, dur) {
      const shown = t >= 0 ? 1 : 0;
      if (params.kind === "cut") return { opacity: shown, x: 0, y: 0, reveal: 1, out_hidden: shown };
      if (params.kind in { focus: 1, zoom: 1, fade: 1 }) {
        const c = cameraChange(params.kind, t, dur);
        return { opacity: c.in.opacity, x: 0, y: 0, reveal: 1, blur: c.in.blur, scale: c.in.scale,
                 out: t < dur ? c.out : null, out_hidden: t >= dur ? 1 : 0 };
      }
      const e = (params.kind === "whip" ? ease.outExpo : params.kind === "tear" ? ease.inOutQuad : ease.outCubic)(progress(t, 0, dur));
      const [dx, dy] = SCENE_DIR[params.from] || SCENE_DIR.right;
      const slide = params.kind === "tear" ? 0 : 1 - e;
      return { opacity: shown, x: r3(dx * slide), y: r3(dy * slide), reveal: r3(params.kind === "tear" ? e : 1),
               out_hidden: t >= dur ? 1 : 0 };
    },
    apply(el, st, params) {
      el.classList.add("om-scene");
      el.setAttribute("data-layout-allow-occlusion", "");  // it covers the scene before it on purpose
      el.style.opacity = String(st.opacity);
      el.style.transform = `translate(${r3(st.x * 100)}%, ${r3(st.y * 100)}%)` + (st.scale != null && st.scale !== 1 ? ` scale(${st.scale})` : "");
      el.style.clipPath = st.reveal >= 1 ? "none" : tornReveal(params, st.reveal);
      el.style.filter = st.blur > 0.01 ? `blur(${st.blur}px)` : "none";
      if (params.out) {
        const out = el.ownerDocument.getElementById(params.out);
        // display, not visibility: a child that sets its own visibility (the odometer's digits) would show through
        if (out) out.style.display = st.out_hidden ? "none" : "";  // its blur and fade: seek() applies them last
      }
    },
  };
  /* The outgoing scene's side of a camera change (the separate `scale`, a blur and fade in its filter). seek()
   * applies it after every cue, so it wins over the outgoing scene's own cue whatever their order in cues.json. */
  function applyOut(out, o) {
    out.style.scale = o.scale === 1 ? "" : String(o.scale);
    const f = [o.blur > 0.01 ? `blur(${o.blur}px)` : "", o.opacity < 1 ? `opacity(${o.opacity})` : ""].filter(Boolean).join(" ");
    out.style.filter = f || "none";
  }
  /* The part of the frame a tear has revealed, from the `from` side, with a jagged edge (in % of the scene). */
  function tornReveal(params, reveal) {
    const [dx, dy] = SCENE_DIR[params.from] || SCENE_DIR.right;
    const edge = reveal * 100;
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const a = (i / 24) * 100;
      const j = (rand(params.seed, i) - 0.5) * 4;
      const d = Math.min(100, Math.max(0, edge + (reveal > 0 ? j : 0)));
      if (dx > 0) pts.push([100 - d, a]);
      else if (dx < 0) pts.push([d, a]);
      else if (dy > 0) pts.push([a, 100 - d]);
      else pts.push([a, d]);
    }
    const close = dx > 0 ? [[100, 100], [100, 0]] : dx < 0 ? [[0, 100], [0, 0]] : dy > 0 ? [[100, 100], [0, 100]] : [[100, 0], [0, 0]];
    return "polygon(" + pts.concat(close).map(([x, y]) => `${r3(x)}% ${r3(y)}%`).join(", ") + ")";
  }

  // ------------------------------------------------------------ cues

  function paramsOf(cue) {
    const part = parts[cue.part];
    if (!part) throw new Error(`motion-kit: unknown part ${cue.part}`);
    return Object.assign({}, part.defaults, cue.params || {});
  }
  function durOf(cue, params) {
    if (typeof cue.dur === "number") return cue.dur;
    return parts[cue.part].dur(params);
  }

  /* The sound moments: [{t, cue, sfx}] by time, the same rules as kit.py's sound placement. */
  function ownHits(cue, p) {
    const dur = typeof cue.dur === "number" ? cue.dur : DUR_DEFAULT[cue.part];
    switch (cue.part) {
      case "highlight": return [[p.draw, "pop"]];
      case "odometer": return [[0, "tick"], [dur, "tick"]];
      case "pop": {
        const n = p.each ? (p.count == null ? 1 : Math.floor(p.count)) : 1;
        const out = [];
        for (let i = 0; i < n; i++) out.push([i * p.stagger, "pop"]);
        return out;
      }
      case "drop": return [[dur, "tap"]];
      case "move": {
        const a = p.from || {};
        const b = p.to || {};
        const dist = Math.hypot((b.x || 0) - (a.x || 0), (b.y || 0) - (a.y || 0));
        return dur <= 0.45 + 1e-9 && dist >= 300 ? [[0, "whoosh"]] : [];
      }
      case "chart": return [[p.draw, "pop"]];
      case "spotlight": return p.flip_at == null ? [] : [[p.flip_at, "whoosh"]];
      case "bubble": return [[p.typing, p.side === "out" ? "sent" : "received"]];
      case "morph": return (p.states || []).slice(1).map((s) => [s.at, "whoosh-short"]);
      case "scene": return p.kind === "cut" ? [] : [[0, p.kind === "whip" ? "whoosh" : "whoosh-short"]];
      case "type": return [[0, "typing"]];
      default: return [];
    }
  }
  function events(doc) {
    const out = [];
    (doc.cues || []).forEach((cue) => {
      const p = paramsOf(cue);
      let own = ownHits(cue, p);
      if (Array.isArray(cue.sfx)) {
        if (!cue.sfx.length) own = [];
        else if (!own.length) own = [[0, cue.sfx[0]]];
        else own = own.map(([t], k) => [t, cue.sfx[k % cue.sfx.length]]);
      }
      own.forEach(([t, sfx]) => out.push({ t: r3(cue.at + t), cue: cue.id, sfx }));
    });
    return out.sort((a, b) => a.t - b.t);  // stable: cue order, then hit order, breaks ties
  }

  /* Every started cue of an element applies in start order, so the latest one wins what they share (opacity,
   * transform) while an earlier one keeps what only it draws (digits, words, a box); before any starts, its
   * first cue shows its first frame. The same frame comes out whatever was seeked before it. */
  function seek(t, doc, documentRef) {
    const D = doc || (typeof window !== "undefined" ? window.ONCA_CUES : null);
    const page = documentRef || (typeof document !== "undefined" ? document : null);
    if (!D || !page) return;
    const byId = new Map();
    (D.cues || []).forEach((cue) => {
      const list = byId.get(cue.id) || [];
      list.push(cue);
      byId.set(cue.id, list);
    });
    (D.cues || []).forEach((cue) => {  // every outgoing scene starts neutral; a started change then marks it
      const outId = cue.part === "scene" && cue.params ? cue.params.out : null;
      const out = outId ? page.getElementById(outId) : null;
      if (out) applyOut(out, NEUTRAL_OUT);
    });
    for (const [id, list] of byId) {
      const el = page.getElementById(id);
      if (!el) throw new Error(`motion-kit: no element #${id}`);
      const ordered = list.slice().sort((a, b) => a.at - b.at);
      const started = ordered.filter((c) => c.at <= t + 1e-9);
      for (const cue of started.length ? started : ordered.slice(0, 1)) {
        const part = parts[cue.part];
        let params = paramsOf(cue);
        if (part.prepare) params = part.prepare(el, params);
        part.apply(el, part.state(params, t - cue.at, durOf(cue, params)), params);
      }
    }
    (D.cues || []).forEach((cue) => {  // the outgoing side of every started camera change, after every cue
      if (cue.part !== "scene" || !cue.params || !cue.params.out || cue.at > t + 1e-9) return;
      const out = page.getElementById(cue.params.out);
      const p = paramsOf(cue);
      const st = parts.scene.state(p, t - cue.at, durOf(cue, p));
      if (out && st.out) applyOut(out, st.out);
    });
  }

  function tear(page) {
    page.querySelectorAll(".om-torn").forEach((el) => {
      const seed = Number(el.getAttribute("data-seed") || 1);
      el.style.clipPath = tornPath(seed, el.offsetWidth, el.offsetHeight, Number(el.getAttribute("data-rough") || 6));
    });
  }

  /* Collage pieces overlap on purpose: each piece carries the engine's mark, which also covers what is inside it
   * (the check looks up the covering element's ancestors). Text is never marked, so it is still checked. */
  const COVER = ".om-prop, .om-torn, .om-sticky, .om-polaroid, .om-cutout, .om-scene";
  function markCover(page) {
    page.querySelectorAll(COVER).forEach((el) => el.setAttribute("data-layout-allow-occlusion", ""));
  }

  if (typeof window !== "undefined" && typeof document !== "undefined") {
    const start = () => {
      tear(document);
      seek(0);
      markCover(document);  // after the first seek, so the scenes it marked count too
    };
    window.addEventListener("hf-seek", (e) => seek(e.detail.time));
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
  }

  return { ease, spring, progress, rand, tornPath, parts, seek, events, paramsOf, durOf, formatNumber, markCover, applyOut };
});
