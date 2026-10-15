/* Plumb walkthrough player (inlined by build-prototype.py into prototype.html and every tour page).
   One tour file drives two modes:
   - guide: a step at a time, Next / Back (arrow keys), Esc to leave; "your turn" steps wait for the learner's real click,
     typing or choice in the prototype, and a wrong click gets a hint;
   - play: runs by itself like a video: a cursor that moves to the element and clicks it, typing letter by letter,
     subtitles, a progress bar with a marker per scene, pause and resume (Space), restart and speed (0.5x to 2x).
   Reduced motion keeps play playing; only the cursor glide and other animation go. Every text is set with textContent.
   Hide panel (its button or H) swaps the dock for a small pill, remembered per viewer. While a tour runs, body has
   .pl-touring (the shell folds its side columns away so the frame keeps its desktop width).
   It drives the shell through window.plumbPrototype and exposes window.plumbPlayer. */
(function () {
  "use strict";
  var api = window.plumbPrototype;
  var dataEl = document.getElementById("plumb-tours");
  if (!api || !dataEl) return;
  var config = JSON.parse(dataEl.textContent);
  var tours = config.tours || [];
  var byId = {};
  tours.forEach(function (t) { byId[t.id] = t; });
  var SPEEDS = [0.5, 1, 1.5, 2];
  var STEP_HOLD = 3200, CARD_HOLD = 2600, GLIDE = 700, TAP = 320, AFTER = 450, LETTER = 70, LEAD = 450;
  var SVG = "http://www.w3.org/2000/svg";
  var motionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function calm() { return !!(motionQuery && motionQuery.matches); }
  function $(id) { return document.getElementById(id); }
  function now() { return window.performance && performance.now ? performance.now() : Date.now(); }
  function el(tag, cls, text, attrs) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function button(cls, text, attrs) {
    var b = el("button", cls, text, attrs);
    b.type = "button";
    return b;
  }
  function times(v) { return String(v) + "×"; }
  function stateLabel(name) {
    var words = String(name).replace(/[-_]+/g, " ").trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
  }
  function screenInfo(id) {
    for (var i = 0; i < api.screens.length; i++) if (api.screens[i].id === id) return api.screens[i];
    return null;
  }
  var stage = $("pp-stage"), frame = $("pp-frame"), mount = api.player || $("plumb-player");
  /* In the app view (a tour page whose tour plays full window) there is no screens list or rail, the page itself
     scrolls, and links back to the screens use its #/ID routes. */
  var appView = api.view === "app";

  /* ------------------------------------------------------------ overlay, card, dock, live region */
  var layer = el("div", "pl-layer", null, { "aria-hidden": "true" });
  var badge = el("span", "pl-badge");
  var subtitle = el("p", "pl-subtitle");
  var cursor = el("span", "pl-cursor pl-still");
  cursor.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 2 L4 19 L8.5 15 L11.5 22 L14.5 20.7 L11.6 14 L18 14 Z"/></svg>';
  [badge, subtitle, cursor].forEach(function (n) { n.hidden = true; layer.appendChild(n); });
  var marks = [];
  var card = el("div", "pl-card");
  var cardBox = el("div", "pl-card-box", null, { role: "group", "aria-roledescription": "title card" });
  var cardEyebrow = el("p", "pl-eyebrow"), cardTitle = el("h2"), cardText = el("p");
  cardBox.appendChild(cardEyebrow); cardBox.appendChild(cardTitle); cardBox.appendChild(cardText);
  /* The app view has no panels: its closing card offers the prototype (the screens list, states, decisions). */
  var cardLink = el("a", "pl-card-link", "Open the prototype", { href: "prototype.html" });
  cardLink.hidden = true;
  cardBox.appendChild(cardLink);
  card.appendChild(cardBox);
  card.hidden = true;
  if (stage) { stage.appendChild(layer); stage.appendChild(card); }
  var live = el("div", "pl-live", null, { "aria-live": "polite", role: "status" });

  var dock = el("section", "pl-dock pp-ui", null, { "aria-label": "Walkthrough", id: "pl-dock" });
  dock.hidden = true;
  var dockTop = el("div", "pl-dock-top");
  var eyebrow = el("p", "pl-eyebrow");
  var leaveBtn = button("pl-btn", "Leave", { "data-pl": "leave", "aria-keyshortcuts": "Escape" });
  var hideBtn = button("pl-btn", "Hide panel", { "data-pl": "hide", "aria-keyshortcuts": "H", "aria-controls": "pl-dock",
    "aria-expanded": "true" });
  var topActs = el("div", "pl-group");
  topActs.appendChild(hideBtn); topActs.appendChild(leaveBtn);
  dockTop.appendChild(eyebrow); dockTop.appendChild(topActs);
  var dTitle = el("h2", "pl-title"), dCaption = el("p", "pl-caption");
  var hint = el("p", "pl-hint", null, { role: "alert" });
  hint.hidden = true;
  var progress = el("div", "pl-progress");
  var track = el("div", "pl-track"), fill = el("div", "pl-fill"), markBox = el("div", "pl-marks", null, { role: "group", "aria-label": "Scenes" });
  track.appendChild(fill); progress.appendChild(track); progress.appendChild(markBox);
  var controls = el("div", "pl-controls");
  var navGroup = el("div", "pl-group");
  var backBtn = button("pl-btn", "Back", { "data-pl": "back", "aria-keyshortcuts": "ArrowLeft" });
  var nextBtn = button("pl-btn pl-primary", "Next", { "data-pl": "next", "aria-keyshortcuts": "ArrowRight" });
  var doBtn = button("pl-btn", "Do it for me", { "data-pl": "do" });
  navGroup.appendChild(backBtn); navGroup.appendChild(nextBtn); navGroup.appendChild(doBtn);
  var playGroup = el("div", "pl-group");
  var playBtn = button("pl-btn pl-primary", "Pause", { "data-pl": "play", "aria-keyshortcuts": "Space" });
  var speeds = el("div", "segs pl-speeds", null, { role: "group", "aria-label": "Speed" });
  var speedBtns = SPEEDS.map(function (v) {
    var b = button("seg", times(v), { "data-speed": String(v), "aria-pressed": "false" });
    speeds.appendChild(b);
    return b;
  });
  playGroup.appendChild(playBtn); playGroup.appendChild(speeds);
  var restartBtn = button("pl-btn", "Restart", { "data-pl": "restart" });
  var modeBtn = button("pl-btn", "Play from here", { "data-pl": "mode" });
  controls.appendChild(navGroup); controls.appendChild(playGroup);
  controls.appendChild(el("span", "pl-spacer"));
  controls.appendChild(restartBtn); controls.appendChild(modeBtn);
  [dockTop, dTitle, dCaption, hint, progress, controls].forEach(function (n) { dock.appendChild(n); });
  /* Hide panel: the dock steps aside and this pill is what is left (the step's title in guide mode, with "Do it for me"
     on a your-turn step; play mode keeps narrating in the subtitle). H or the pill's button brings the dock back; the
     choice is remembered per viewer. A hint after a wrong click, and the end of play, bring the dock back for that
     moment without changing the choice. */
  var pill = el("div", "pl-pill pp-ui", null, { role: "group", "aria-label": "Walkthrough (panel hidden)" });
  var pillTitle = el("span", "pl-pill-title");
  var pillDo = button("pl-btn", "Do it for me", { "data-pl": "do" });
  var showBtn = button("pl-btn pl-primary", "Show panel", { "data-pl": "show", "aria-keyshortcuts": "H",
    "aria-controls": "pl-dock", "aria-expanded": "false" });
  pill.appendChild(pillTitle); pill.appendChild(pillDo); pill.appendChild(showBtn);
  pill.hidden = true;
  [dock, pill, live].forEach(function (n) { (mount || document.body).appendChild(n); });
  var PANEL_KEY = "plumb.player.panel";
  function storedHidden() {
    try { return window.localStorage.getItem(PANEL_KEY) === "hidden"; } catch (err) { return false; }
  }
  function storeHidden(on) {
    try {
      if (on) window.localStorage.setItem(PANEL_KEY, "hidden");
      else window.localStorage.removeItem(PANEL_KEY);
    } catch (err) { /* storage off (private window, blocked site data): the choice lasts for this page only */ }
  }
  function inChrome(node) { return !!node && (dock.contains(node) || pill.contains(node)); }
  /* Focus that was on a control the panel change just hid (or that fell back to the page). */
  function focusLost() {
    var a = document.activeElement;
    return !a || a === document.body || !a.getClientRects().length;
  }
  /* While a tour runs, the first stop in the tab order jumps to its controls (the dock is last in the page). */
  var skip = el("a", "pp-skip pp-ui pl-skip", "Skip to the walkthrough", { href: "#plumb-player" });
  skip.hidden = true;
  skip.addEventListener("click", function (e) { e.preventDefault(); if (T.tour) focusPrimary(); });
  document.body.insertBefore(skip, document.body.firstChild);

  /* ------------------------------------------------------------ the player's state */
  var T = { tour: null, mode: null, seq: [], scenes: [], pos: 0, speed: 1, paused: false, ended: false, run: 0, timer: null,
            wait: null, plan: 1, spent: 0, opener: null, turn: null, raf: 0, redraw: null, zoomTimer: null,
            panelHidden: storedHidden(), reveal: false, step: null };

  function sequence(tour) {
    var seq = [];
    if (tour.intro) seq.push({ kind: "card", card: "intro", title: tour.intro.title, text: tour.intro.text, hold: tour.intro.hold });
    tour.steps.forEach(function (s, i) {
      tour.chapters.forEach(function (c, ci) {
        if (c.first === i) seq.push({ kind: "card", card: "chapter", title: c.title, text: c.text, hold: c.hold, chapter: ci });
      });
      seq.push({ kind: "step", step: s });
    });
    if (tour.closing) seq.push({ kind: "card", card: "closing", title: tour.closing.title, text: tour.closing.text, hold: tour.closing.hold });
    return seq;
  }
  function scenesOf(tour, seq) {
    var out = [];
    seq.forEach(function (item, pos) {
      if (tour.chapters.length ? item.card === "chapter" : item.kind === "step") {
        out.push({ pos: pos, label: tour.chapters.length ? item.title : (item.step.title || item.step.caption) });
      }
    });
    return out;
  }
  function state() {
    var item = T.tour ? T.seq[T.pos] : null;
    return {
      active: !!T.tour, tour: T.tour ? T.tour.id : null, mode: T.mode, pos: T.tour ? T.pos : null, total: T.seq.length,
      step: item && item.kind === "step" ? item.step.n : null, card: item && item.kind === "card" ? item.card : null,
      paused: T.paused, speed: T.speed, ended: T.ended,
      yourTurn: !!(item && item.kind === "step" && item.step.yourTurn && T.mode === "guide")
    };
  }
  function emit() {
    try { document.dispatchEvent(new CustomEvent("plumb:tour", { detail: state() })); }
    catch (err) { console.error("Plumb: a walkthrough listener failed:", err); }
  }

  /* ------------------------------------------------------------ timers that pause and follow the speed */
  function wait(ms, fn) {
    var w = { left: ms, total: ms, fn: fn, run: T.run, at: null, rate: T.speed };
    T.wait = w;
    if (!T.paused) arm();
  }
  function arm() {
    var w = T.wait;
    if (!w) return;
    clearTimeout(T.timer);
    w.at = now();
    w.rate = T.speed;
    T.timer = setTimeout(function () {
      if (w.run !== T.run || T.wait !== w) return;
      T.wait = null;
      T.spent += w.total;
      w.fn();
    }, w.left / T.speed);
  }
  function freeze() {
    clearTimeout(T.timer);
    var w = T.wait;
    if (w && w.at !== null) { w.left = Math.max(0, w.left - (now() - w.at) * w.rate); w.at = null; }
  }
  function stopTimers() {
    clearTimeout(T.timer);
    clearTimeout(T.zoomTimer);
    T.timer = null;
    T.wait = null;
  }

  /* ------------------------------------------------------------ finding and drawing */
  function find(step, sel) {
    var section = api.screen(step.screen);
    if (!section || !sel) return null;
    var list;
    try { list = section.querySelectorAll(sel); } catch (err) { return null; }
    var f = frameBox();
    for (var i = 0; i < list.length; i++) if (seen(list[i], f)) return list[i];
    return null;  /* nothing of it is on screen (another state, or the screen moved on): point at nothing */
  }
  /* The frame's padding box in the window (inside its border, scaled with a zoom): what a screen's content can cover. A
     drawer moved off with translateX(100%) starts exactly at its edge. */
  function frameBox() {
    var b = frame.getBoundingClientRect(), k = frame.offsetWidth ? b.width / frame.offsetWidth : 1;
    var left = b.left + frame.clientLeft * k, top = b.top + frame.clientTop * k;
    return { left: left, top: top, right: left + frame.clientWidth * k, bottom: top + frame.clientHeight * k };
  }
  /* The element whose box stands for a node: the node itself, or for display: contents (no box of its own) its first
     child that has one. */
  function shape(node) {
    if (getComputedStyle(node).display !== "contents") return node;
    for (var c = node.firstElementChild; c; c = c.nextElementSibling) {
      var s = shape(c);
      if (s && s.getClientRects().length) return s;
    }
    return null;
  }
  function rectOf(node) { return (shape(node) || node).getBoundingClientRect(); }
  /* A node the viewer can see, or could once its scrollers bring it in: laid out, not visibility: hidden (computed, so
     also inside a hidden parent), and on the frame (rect f) rather than pushed off it (an off-canvas drawer moved aside
     with a transform). A node an inner scroller has scrolled away (a wide table's far column, a lower item of a
     fixed-height list) counts when that scroller's range reaches it. Judging never scrolls anything. */
  function seen(node, f) {
    var s = shape(node);
    if (!s || !s.getClientRects().length) return false;
    var r = s.getBoundingClientRect();
    if (!(r.width > 0 || r.height > 0)) return false;
    var vis = getComputedStyle(s).visibility;
    if (vis === "hidden" || vis === "collapse") return false;
    var q = reach(s, r);
    return !!q && q.right > f.left && q.left < f.right && q.bottom > f.top && q.top < f.bottom;
  }
  function scrolls(cs) {
    return { x: /auto|scroll/.test(cs.overflowX), y: /auto|scroll/.test(cs.overflowY) };
  }
  /* True when an element holds absolutely (abs) or fixed positioned descendants as their containing block. */
  function holds(cs, fixed) {
    var other = (cs.transform && cs.transform !== "none") || (cs.filter && cs.filter !== "none") ||
      (cs.perspective && cs.perspective !== "none") || /layout|paint|strict|content/.test(cs.contain || "") ||
      /transform|perspective|filter/.test(cs.willChange || "");
    return fixed ? !!other : cs.position !== "static" || !!other;
  }
  /* True when node moves as scroller a scrolls: a is on its containing-block chain (a fixed toast, or an absolute drawer
     placed against something outside a, does not move with it). */
  function movesWith(node, a) {
    var n = node;
    while (n && n !== a) {
      var pos = getComputedStyle(n).position, p = n.parentElement;
      if (pos === "absolute" || pos === "fixed") {
        while (p && p !== a && !holds(getComputedStyle(p), pos === "fixed")) p = p.parentElement;
        if (p === a) return holds(getComputedStyle(a), pos === "fixed");
      }
      n = p;
    }
    return n === a;
  }
  /* The nearest-edge scroll (dx, dy) of scroller a that brings rect r into its view, within its scroll range. */
  function nudge(a, cs, r) {
    var sc = scrolls(cs), ar = a.getBoundingClientRect();
    var left = ar.left + a.clientLeft, top = ar.top + a.clientTop, right = left + a.clientWidth, bottom = top + a.clientHeight;
    function want(lo, hi, from, to) { return lo < from ? lo - from : hi > to ? Math.min(hi - to, lo - from) : 0; }
    function range(v, d, max, rtl) {
      var lo = rtl ? -max : 0, hi = rtl ? 0 : max;
      return clamp(v + d, lo, hi) - v;
    }
    var rtl = cs.direction === "rtl";
    var dx = sc.x ? range(a.scrollLeft, want(r.left, r.right, left, right), Math.max(0, a.scrollWidth - a.clientWidth), rtl) : 0;
    var dy = sc.y ? range(a.scrollTop, want(r.top, r.bottom, top, bottom), Math.max(0, a.scrollHeight - a.clientHeight), false) : 0;
    return { dx: dx, dy: dy };
  }
  /* Where a node's rect would be once every scroller between it and the frame brought it in (no scrolling), or null
     when a box it moves with still leaves it fully outside: an overflow hidden / clip box (a carousel's other slide, a
     collapsed accordion) or a scroller whose range does not reach it. Innermost first: an outer scroller moves the
     node and the boxes inside it together, so each box is checked against the node where it then is. */
  function reach(s, r) {
    var q = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    for (var a = s.parentElement; a && a !== frame && a !== document.body; a = a.parentElement) {
      var cs = getComputedStyle(a), cx = cs.overflowX !== "visible", cy = cs.overflowY !== "visible";
      if ((!cx && !cy) || !movesWith(s, a)) continue;
      var sc = scrolls(cs);
      if (sc.x || sc.y) {
        var d = nudge(a, cs, q);
        q = { left: q.left - d.dx, top: q.top - d.dy, right: q.right - d.dx, bottom: q.bottom - d.dy };
      }
      var ar = a.getBoundingClientRect(), left = ar.left + a.clientLeft, top = ar.top + a.clientTop;
      if ((cx && (q.right <= left || q.left >= left + a.clientWidth)) ||
          (cy && (q.bottom <= top || q.top >= top + a.clientHeight))) return null;
    }
    return q;
  }
  /* True when a node is scrolled or clipped out of view by a box between it and the frame (drawn only when in view). */
  function clipped(node) {
    var s = shape(node);
    if (!s) return true;
    var r = s.getBoundingClientRect();
    for (var a = s.parentElement; a && a !== frame && a !== document.body; a = a.parentElement) {
      var cs = getComputedStyle(a);
      if (cs.overflowX === "visible" && cs.overflowY === "visible") continue;
      if (!movesWith(s, a)) continue;
      var ar = a.getBoundingClientRect(), left = ar.left + a.clientLeft, top = ar.top + a.clientTop;
      if (r.right <= left || r.left >= left + a.clientWidth || r.bottom <= top || r.top >= top + a.clientHeight) return true;
    }
    return false;
  }
  /* Scrolls a node into view, nearest edge and at once, inside every scroller it moves with between it and the frame;
     the window is left alone. A scroller that moved without moving the node is put back. Only decorate() calls this,
     once per step. */
  function reveal(node) {
    var s = shape(node);
    if (!s) return;
    for (var a = s.parentElement; a && a !== frame && a !== document.body; a = a.parentElement) {
      var cs = getComputedStyle(a), sc = scrolls(cs);
      if ((!sc.x && !sc.y) || !movesWith(s, a)) continue;
      var before = s.getBoundingClientRect(), d = nudge(a, cs, before);
      if (!d.dx && !d.dy) continue;
      var x0 = a.scrollLeft, y0 = a.scrollTop;
      scrollBox(a, x0 + d.dx, y0 + d.dy);
      var after = s.getBoundingClientRect();
      if (after.left === before.left && after.top === before.top) scrollBox(a, x0, y0);
    }
  }
  function scrollBox(a, left, top) {
    try { a.scrollTo({ left: left, top: top, behavior: "instant" }); }
    catch (err) { a.scrollLeft = left; a.scrollTop = top; }
  }
  /* Every scroll the player makes is instant, whatever scroll-behavior a screen sets (it reads positions right after). */
  function scrollToNode(node, opts) {
    opts.behavior = "instant";
    try { node.scrollIntoView(opts); } catch (err) { delete opts.behavior; node.scrollIntoView(opts); }
  }
  function scrollWindowBy(dy) {
    try { window.scrollBy({ top: dy, left: 0, behavior: "instant" }); } catch (err) { window.scrollBy(0, dy); }
  }
  /* The window's top edge below the shell's sticky bar, and the room the dock (or its pill) takes at the bottom. */
  function topInset() {
    var bar = document.querySelector(".pp-bar");
    if (!bar || !bar.getClientRects().length) return 0;
    var pos = getComputedStyle(bar).position;
    return pos === "sticky" || pos === "fixed" ? Math.max(0, bar.getBoundingClientRect().bottom) : 0;
  }
  /* True when nothing between n and the page makes a containing block for position: fixed (so a fixed layer of n is
     placed against the window: the app view, where the window is the frame). */
  function fixedToWindow(n) {
    for (var p = n.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      if (holds(getComputedStyle(p), true)) return false;
    }
    return true;
  }
  /* True when a sticky element sticks to the window: no box between it and the page clips or scrolls (a sticky table
     head inside a scrolling list sticks to that list instead). */
  function sticksToWindow(n) {
    for (var p = n.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      var cs = getComputedStyle(p);
      if (cs.overflowX !== "visible" || cs.overflowY !== "visible") return false;
    }
    return true;
  }
  /* The window's top edge below whatever the screen itself keeps at the top of the window while the page scrolls: its
     own fixed or sticky headers, bars and banners (in the app view the page scrolls, so one of them can cover a
     target). Only layers that sit across the target's columns count, never one holding the target or inside it, nor
     a tall one (a full-height sidebar or a scrim). Measured once per step, before the page moves: a sticky element is
     taken at the top it sticks to. Several stacked bars add up. */
  function screenTop(node, top) {
    var target = shape(node) || node, section = target.closest ? target.closest("[data-screen]") : null;
    if (!section) return top;
    var r = target.getBoundingClientRect(), vh = window.innerHeight, bands = [];
    Array.prototype.forEach.call(section.querySelectorAll("*"), function (n) {
      var cs = getComputedStyle(n), pos = cs.position;
      if ((pos !== "fixed" && pos !== "sticky") || n.contains(target) || target.contains(n)) return;
      if (!n.getClientRects().length || cs.visibility === "hidden" || cs.visibility === "collapse") return;
      var b = n.getBoundingClientRect();
      if (!(b.height > 0) || b.height > vh / 2 || b.right <= r.left || b.left >= r.right) return;
      var from;
      if (pos === "fixed") {
        if (!fixedToWindow(n)) return;
        from = b.top;
      } else {
        from = parseFloat(cs.top);
        if (isNaN(from) || !sticksToWindow(n)) return;
        /* it sticks only within its parent: one whose parent ends above the target has scrolled away by then */
        var cb = n.parentElement && n.parentElement.getBoundingClientRect();
        if (cb && cb.bottom <= r.top) return;
      }
      bands.push([from, from + b.height]);
    });
    bands.sort(function (a, b) { return a[0] - b[0]; });
    bands.forEach(function (b) { if (b[0] <= top + 24 && b[1] > top) top = b[1]; });
    return top;
  }
  function chromeHeight() {
    if (!dock.hidden) return dock.offsetHeight + 16;
    return pill.hidden ? 0 : pill.offsetHeight + 16;
  }
  /* The panel on show (the dock, or the pill while the panel is hidden), or null. */
  function chromeEl() { return !dock.hidden ? dock : !pill.hidden ? pill : null; }
  /* The dock (and the pill) sit at the bottom of the window, or at its top (below the shell's sticky bar) for a step
     whose target they would cover there. */
  function atTop() { return dock.classList.contains("pl-at-top"); }
  function setTop(on) {
    [dock, pill].forEach(function (n) {
      n.classList.toggle("pl-at-top", on);
      if (on) n.style.setProperty("--pl-top", topInset() + "px");
      else n.style.removeProperty("--pl-top");
    });
  }
  /* The part of the window clear of the shell's bar and the panel: [top, bottom]. */
  function roomTop() {
    var top = topInset(), c = atTop() ? chromeEl() : null;
    return c ? Math.max(top, c.getBoundingClientRect().bottom + 8) : top;
  }
  function roomBottom() { return atTop() ? window.innerHeight : window.innerHeight - chromeHeight(); }
  /* True when a node stays where it is as the page scrolls: it, or a box around it, is fixed to the window (a toast or a
     bar of the app view, where nothing between it and the page holds fixed layers). */
  function pinned(node) {
    for (var n = node; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      if (getComputedStyle(n).position === "fixed") return fixedToWindow(n);
    }
    return false;
  }
  /* How much of the panel's box covers the given rects (in px²). */
  function cover(rects) {
    var c = chromeEl();
    if (!c) return 0;
    var d = c.getBoundingClientRect();
    return rects.reduce(function (sum, r) {
      return sum + Math.max(0, Math.min(r.right, d.right) - Math.max(r.left, d.left)) *
        Math.max(0, Math.min(r.bottom, d.bottom) - Math.max(r.top, d.top));
    }, 0);
  }
  /* Puts the panel at the bottom of the window, or at its top when at the bottom it would cover one of the step's
     targets and at the top it covers less: a toast fixed to a bottom corner, a bar stuck to the bottom of the window.
     Only the given nodes count; by default every target of the step on show that is fixed to the window or fits the
     room (a target taller than the window is always partly under the panel, which then stays at the bottom). Never
     scrolls. */
  function placeChrome(step, nodes) {
    setTop(false);
    if (!step || !chromeEl()) return;
    var room = window.innerHeight - chromeHeight() - topInset();
    var list = nodes || step.targets.map(function (s) { return find(step, s); }).filter(function (n) {
      return n && !clipped(n) && (pinned(shape(n) || n) || rectOf(n).height <= room);
    });
    var rects = list.map(rectOf);
    var below = cover(rects);
    if (!below) return;
    setTop(true);
    if (cover(rects) >= below) setTop(false);
  }
  /* True when a node or a box around it is sticky: it may stay in the window while the page (and its labels) scroll. */
  function sticky(node) {
    for (var n = node; n && n !== document.body; n = n.parentElement) {
      if (getComputedStyle(n).position === "sticky") return true;
    }
    return false;
  }
  /* Brings a step's labels into view with its target (already in view, or fixed to the window): the target and every
     label together when they fit the room, else the target and the first label. A target that may stay put while the
     page scrolls (fixed to the window, or in a sticky sidebar) is tried first as staying put; a scroll that leaves the
     target or those labels out of view is undone. A label counts with the room its tag takes above the labelled
     element. */
  function fitLabels(el0, labels, top, bottom, still) {
    if (!labels.length) return;
    var pad = 8, lo = top + pad, hi = bottom - pad;
    function need(n) { var r = rectOf(n); return { top: r.top - 16, bottom: r.top + 24 }; }
    function within(b) { return b.top >= top && b.bottom <= bottom; }
    function ok(set) { return set.every(function (n) { return within(need(n)); }) && (still || within(el0.getBoundingClientRect())); }
    /* the smallest window scroll that brings these labels (and the target, when it moves with them) in, or null */
    function shift(set, withTarget) {
      var u = (withTarget ? [el0.getBoundingClientRect()] : []).concat(set.map(need)).reduce(function (a, b) {
        return { top: Math.min(a.top, b.top), bottom: Math.max(a.bottom, b.bottom) };
      }, { top: Infinity, bottom: -Infinity });
      if (u.bottom - u.top > hi - lo) return null;
      return u.top < lo ? u.top - lo : u.bottom > hi ? u.bottom - hi : 0;
    }
    if (ok(labels)) return;
    var sets = [labels, labels.slice(0, 1)], tries = [], y0 = window.scrollY;
    if (still || sticky(el0)) sets.forEach(function (s) { tries.push([s, false]); });
    if (!still) sets.forEach(function (s) { tries.push([s, true]); });
    for (var i = 0; i < tries.length; i++) {
      var d = shift(tries[i][0], tries[i][1]);
      if (d === null) continue;
      if (d) scrollWindowBy(d);
      if (ok(tries[i][0])) return;
      scrollWindowBy(y0 - window.scrollY);  /* undone: the target first */
    }
  }
  function onStepScreen(step) {
    var cur = api.current();
    return cur.page === "screen" && cur.screen === step.screen;
  }
  function box(node) {
    var s = stage.getBoundingClientRect(), r = rectOf(node);
    return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function put(node, x, y) { node.style.left = x + "px"; node.style.top = y + "px"; }
  function addOverlay(node) { node.setAttribute("data-pl-step", ""); layer.appendChild(node); return node; }
  function clearOverlays() {
    Array.prototype.slice.call(layer.querySelectorAll("[data-pl-step]")).forEach(function (n) { n.remove(); });
    layer.classList.remove("pl-flash");
  }
  function describe(node) {
    if (!node) return "element";
    var text = node.getAttribute("aria-label") || node.getAttribute("placeholder") || node.textContent || "";
    if (!text.trim() && node.labels && node.labels[0]) text = node.labels[0].textContent;
    text = text.replace(/\s+/g, " ").trim();
    return text ? "“" + (text.length > 40 ? text.slice(0, 39) + "…" : text) + "”" : "element";
  }
  function moveCursor(node, glide) {
    var b = box(node);
    if (cursor.hidden) {
      cursor.classList.add("pl-still");
      put(cursor, stage.clientWidth / 2, stage.clientHeight / 2);
      cursor.hidden = false;
      void cursor.offsetWidth;
    }
    cursor.classList.toggle("pl-still", !glide);
    put(cursor, b.x + Math.min(b.w / 2, 40), b.y + b.h / 2);
  }
  function unzoom() {
    frame.classList.remove("pl-zoom-in");
    frame.style.transform = "";
    frame.style.transformOrigin = "";
    stage.classList.remove("pl-zooming");
  }
  /* A zoom scales the frame with a transform, which makes the frame the containing block of everything the screen fixes
     in place. In prototype.html the frame is that already (contain: layout), so nothing moves. Where the window is the
     frame (the app view), a fixed header, toast or dialog would jump to the top of the page for as long as the zoom
     lasts: there a screen showing a fixed layer is not zoomed, and the step points with a spotlight instead. */
  function zoomMovesFixed(step) {
    if (!fixedToWindow(frame) || holds(getComputedStyle(frame), true)) return false;
    var section = api.screen(step.screen);
    if (!section) return false;
    return Array.prototype.some.call(section.querySelectorAll("*"), function (n) {
      var cs = getComputedStyle(n);
      return cs.position === "fixed" && n.getClientRects().length > 0 && cs.visibility !== "hidden";
    });
  }
  function zoom(nodes) {
    unzoom();
    var f = frame.getBoundingClientRect();
    var x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    nodes.forEach(function (n) {
      var r = rectOf(n);
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    });
    var w = Math.max(1, x2 - x1), h = Math.max(1, y2 - y1), s = stage.getBoundingClientRect();
    var cx = (x1 + x2) / 2, cy = (y1 + y2) / 2, m = 8;
    /* scaled about its own centre, the area must stay inside the frame's 80% and inside the stage on every side */
    var k = Math.min(1.6, f.width * 0.8 / w, f.height * 0.8 / h, 2 * (cx - s.left - m) / w, 2 * (s.right - m - cx) / w,
                     2 * (cy - s.top - m) / h, 2 * (s.bottom - m - cy) / h);
    if (!(k >= 1.1)) return false;  /* the area already fills the view: zooming would only crop it */
    stage.classList.add("pl-zooming");
    frame.classList.add("pl-zoom-in");
    frame.style.transformOrigin = ((x1 + x2) / 2 - f.left) + "px " + ((y1 + y2) / 2 - f.top) + "px";
    frame.style.transform = "scale(" + k.toFixed(3) + ")";
    return true;
  }
  /* Draws the step's pointing and text on the stage; called again on resize and after a zoom settles. */
  function draw(step, point) {
    clearOverlays();
    if (!onStepScreen(step)) { unzoom(); return; }  /* a played or real click moved on: the step's marks go with it */
    /* drawn where things are now: nothing here scrolls, and what a scroller holds out of view is left out */
    var targets = step.targets.map(function (s) { return find(step, s); }).filter(function (n) { return n && !clipped(n); });
    var boxes = targets.map(box);
    var W = stage.clientWidth, H = stage.clientHeight;
    if (point === "spotlight" && boxes.length) {
      var svg = document.createElementNS(SVG, "svg");
      svg.setAttribute("class", "pl-dim");
      svg.setAttribute("width", W); svg.setAttribute("height", H);
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      var d = "M0 0H" + W + "V" + H + "H0Z";
      boxes.forEach(function (b) {
        var p = 6;
        d += "M" + (b.x - p) + " " + (b.y - p) + "h" + (b.w + 2 * p) + "v" + (b.h + 2 * p) + "h" + -(b.w + 2 * p) + "Z";
      });
      var path = document.createElementNS(SVG, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill-rule", "evenodd");
      svg.appendChild(path);
      addOverlay(svg);
      boxes.forEach(function (b) { ring("pl-edge", b); });
    }
    if (point === "ring") boxes.forEach(function (b) { ring("pl-ring", b); });
    /* zoomed or not (an area that already fills the view, or near the window's edge, is not enlarged), it is outlined */
    if (point === "zoom") boxes.forEach(function (b) { ring("pl-edge", b); });
    if (point === "beacon") boxes.forEach(function (b) { put(addOverlay(el("span", "pl-beacon")), b.x + b.w - 2, b.y + 2); });
    var reserved = { top: 0, bottom: 0 };
    if (point === "arrow" && boxes.length) {
      var b0 = boxes[0], up = b0.y < 72;
      var arrow = addOverlay(el("div", "pl-arrow" + (up ? " pl-arrow-up" : "")));
      var label = el("span", "pl-arrow-label", step.pointLabel || step.title || "Here");
      var glyph = document.createElementNS(SVG, "svg");
      glyph.setAttribute("viewBox", "0 0 22 30");
      glyph.innerHTML = up ? '<path d="M11 2 L20 13 H14 V28 H8 V13 H2 Z" fill="currentColor"/>'
                           : '<path d="M11 28 L20 17 H14 V2 H8 V17 H2 Z" fill="currentColor"/>';
      if (up) { arrow.appendChild(glyph); arrow.appendChild(label); } else { arrow.appendChild(label); arrow.appendChild(glyph); }
      var aw = arrow.offsetWidth, ah = arrow.offsetHeight;
      put(arrow, clamp(b0.x + b0.w / 2 - aw / 2, 6, Math.max(6, W - aw - 6)), up ? b0.y + b0.h + 6 : b0.y - ah - 6);
      reserved[up ? "bottom" : "top"] = ah + 6;
    }
    step.labels.forEach(function (lab) {
      var t = find(step, lab.target);
      if (!t || clipped(t)) return;
      var b = box(t), tag = addOverlay(el("span", "pl-label", lab.text));
      placeClear(tag, clamp(b.x - 6, 4, Math.max(4, W - tag.offsetWidth - 4)), Math.max(4, b.y - 12), W, H);
    });
    if (step.callout && boxes.length) callout(step.callout, boxes[0], W, H, reserved);
    if (step.note) {
      var f = box(frame), note = addOverlay(el("div", "pl-note", step.note.text));
      var nw = note.offsetWidth, nh = note.offsetHeight;
      put(note, clamp(f.x + f.w * step.note.x / 100 - nw / 2, 8, Math.max(8, W - nw - 8)),
          clamp(f.y + f.h * step.note.y / 100 - nh / 2, 8, Math.max(8, H - nh - 8)));
    }
    if (point === "cursor" && targets.length) moveCursor(targets[0], T.mode === "play" && !calm());
  }
  /* Puts a tag at (x, y), or nudged left or down when it would sit under the play badge or the dock. */
  function placeClear(tag, x, y, W, H) {
    var tw = tag.offsetWidth, th = tag.offsetHeight, s = stage.getBoundingClientRect(), keep = [];
    if (!badge.hidden) keep.push(box(badge));
    [dock, pill].forEach(function (n) {
      if (n.hidden) return;
      var d = n.getBoundingClientRect();
      keep.push({ x: d.left - s.left, y: d.top - s.top, w: d.width, h: d.height });
    });
    function clear(px, py) {
      return keep.every(function (k) { return px + tw <= k.x - 2 || px >= k.x + k.w + 2 || py + th <= k.y - 2 || py >= k.y + k.h + 2; });
    }
    var tries = [[x, y]];
    keep.forEach(function (k) { tries.push([k.x - tw - 6, y], [x, k.y + k.h + 4], [x, k.y - th - 4]); });
    for (var i = 0; i < tries.length; i++) {
      var px = clamp(tries[i][0], 4, Math.max(4, W - tw - 4)), py = clamp(tries[i][1], 4, Math.max(4, H - th - 4));
      if (clear(px, py)) { put(tag, px, py); return; }
    }
    put(tag, clamp(x, 4, Math.max(4, W - tw - 4)), clamp(y, 4, Math.max(4, H - th - 4)));
  }
  /* A title card covers the part of the stage in the window (between the sticky bar and the dock); when the stage is
     almost out of view, the window between them. */
  function placeCard() {
    if (card.hidden) return;
    var s = stage.getBoundingClientRect(), top = topInset(), bottom = window.innerHeight - chromeHeight();
    var vw = document.documentElement.clientWidth || window.innerWidth;
    var y1 = Math.max(s.top, top), y2 = Math.min(s.bottom, bottom);
    if (y2 - y1 < Math.min(240, bottom - top)) { y1 = top; y2 = bottom; }
    var x1 = Math.max(s.left, 0), x2 = Math.min(s.right, vw);
    if (x2 - x1 < 160) { x1 = 0; x2 = vw; }
    card.style.left = x1 + "px";
    card.style.top = y1 + "px";
    card.style.width = Math.max(0, x2 - x1) + "px";
    card.style.height = Math.max(0, y2 - y1) + "px";
  }
  /* The subtitle sits at the bottom of the part of the stage you can see, above the dock (or its pill); with the panel
     at the top of the window, just below it. */
  function placeSubtitle() {
    if (subtitle.hidden) return;
    var s = stage.getBoundingClientRect(), c = atTop() ? chromeEl() : null;
    subtitle.style.bottom = "auto";
    if (c) {
      var under = c.getBoundingClientRect().bottom + 16 - s.top;
      subtitle.style.top = clamp(under, 8, Math.max(8, stage.clientHeight - subtitle.offsetHeight - 8)) + "px";
      return;
    }
    var floor = window.innerHeight - chromeHeight() - 16;
    var bottom = Math.min(s.bottom - 16, floor) - s.top;
    subtitle.style.bottom = "auto";
    subtitle.style.top = clamp(bottom - subtitle.offsetHeight, 8, Math.max(8, stage.clientHeight - subtitle.offsetHeight - 8)) + "px";
  }
  function ring(cls, b) {
    var r = addOverlay(el("span", cls));
    put(r, b.x - 4, b.y - 4);
    r.style.width = (b.w + 8) + "px";
    r.style.height = (b.h + 8) + "px";
  }
  function callout(c, b, W, H, reserved) {
    var n = addOverlay(el("div", "pl-callout pl-side-" + c.side, c.text));
    var w = n.offsetWidth, h = n.offsetHeight, side = c.side, x, y, gap = 12;
    if (side === "right" && b.x + b.w + gap + w > W - 8) side = "bottom";
    if (side === "left" && b.x - gap - w < 8) side = "bottom";
    if (side === "top" && b.y - gap - reserved.top - h < 4) side = "bottom";
    n.className = "pl-callout pl-side-" + side;
    /* an arrow on the same side keeps its place: the callout goes past it */
    if (side === "bottom") { x = b.x + b.w / 2 - w / 2; y = b.y + b.h + gap + reserved.bottom; }
    else if (side === "top") { x = b.x + b.w / 2 - w / 2; y = b.y - h - gap - reserved.top; }
    else if (side === "right") { x = b.x + b.w + gap; y = b.y + b.h / 2 - h / 2; }
    else { x = b.x - w - gap; y = b.y + b.h / 2 - h / 2; }
    put(n, clamp(x, 8, Math.max(8, W - w - 8)), clamp(y, 4, Math.max(4, H - h - 4)));
  }
  /* Scrolls the step's first target into the room between the sticky bar (and the screen's own fixed or sticky
     header) and the dock. One that fits is centred in that room; then its labels come in with it (fitLabels). One
     fixed to the window is never scrolled to (scrolling cannot move it): only its labels are. One taller than that room:
     with labels, its top edge and its topmost label come into view together when they fit, else the topmost label;
     without labels, it goes to its nearest edge, and not at all while part of it is in view, so a tall area already
     filling the window does not jump. */
  function bringIntoView(node, labels) {
    var el0 = shape(node) || node, still = pinned(el0);
    var top = screenTop(el0, roomTop()), bottom = roomBottom();
    var r = el0.getBoundingClientRect(), margin = 32;
    if (still || r.height <= bottom - top) {
      if (!still && (r.top < top || r.bottom > bottom)) {
        scrollToNode(el0, { block: "nearest", inline: "nearest" });  /* the window and any box between, as before */
        r = el0.getBoundingClientRect();
        scrollWindowBy((r.top + r.bottom) / 2 - (top + bottom) / 2);
      }
      fitLabels(el0, labels, top, bottom, still);
      return;
    }
    if (!labels.length) {
      if (r.bottom <= top || r.top >= bottom) scrollToNode(el0, { block: "nearest", inline: "nearest" });
      return;
    }
    var label = Infinity;
    labels.forEach(function (n) { label = Math.min(label, rectOf(n).top); });
    var hi = Math.min(r.top, label), lo = Math.max(r.top, label);
    var want = lo - hi <= bottom - top - 3 * margin ? [hi, lo] : [label, label];
    if (want[0] >= top + margin && want[1] <= bottom - 2 * margin) return;  /* in view already */
    scrollWindowBy(want[0] - (top + margin));
  }
  /* The one place a step scrolls, once, when it opens: its first target into view inside its scrollers, then the
     window (with its labels in view too, when it has labels in view); then the panel keeps clear of the targets and
     everything is measured. A target fixed to the window moves the panel first, so the room is measured right. */
  function decorate(step) {
    var targets = step.targets.map(function (s) { return find(step, s); }).filter(Boolean);
    if (targets.length) reveal(targets[0]);
    var labelled = step.labels.map(function (lab) { return find(step, lab.target); })
      .filter(function (n) { return n && !clipped(n); });
    T.step = step;
    placeChrome(step, targets.filter(function (n) { return !clipped(n) && pinned(shape(n) || n); }));
    if (targets.length) bringIntoView(targets[0], labelled);
    placeChrome(step, null);
    var point = step.point === "zoom" && zoomMovesFixed(step) ? "spotlight" : step.point;
    T.redraw = function () { draw(step, point); };
    var shown = targets.filter(function (n) { return !clipped(n); });
    if (point === "zoom" && shown.length && zoom(shown)) {
      T.zoomTimer = setTimeout(function () { if (T.redraw) T.redraw(); }, calm() ? 0 : 400);
    }
    draw(step, point);
  }
  function clearStep() {
    clearOverlays();
    unzoom();
    T.redraw = null;
    T.step = null;
    setTop(false);
    if (T.turn) { T.turn(); T.turn = null; }
    hint.hidden = true;
    hint.textContent = "";
    card.hidden = true;
    subtitle.hidden = true;
    cursor.classList.remove("pl-tap");
    Array.prototype.forEach.call(document.querySelectorAll(".pl-typing"), function (n) { n.classList.remove("pl-typing"); });
  }

  /* ------------------------------------------------------------ actions on the real controls */
  function fire(node, type) { node.dispatchEvent(new Event(type, { bubbles: true })); }
  function setValue(node, value) {
    var proto = node.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set && (node.tagName === "INPUT" || node.tagName === "TEXTAREA")) desc.set.call(node, value);
    else if (node.isContentEditable) node.textContent = value;
    else node.value = value;
    fire(node, "input");
  }
  function choose(node, value) {
    var want = String(value).trim().toLowerCase();
    function same(text) { return String(text || "").replace(/\s+/g, " ").trim().toLowerCase() === want; }
    if (node.tagName === "SELECT") {
      for (var i = 0; i < node.options.length; i++) {
        var o = node.options[i];
        if (same(o.value) || same(o.textContent)) { node.value = o.value; fire(node, "input"); fire(node, "change"); return; }
      }
      return;
    }
    var inputs = node.matches("input") ? [node] : Array.prototype.slice.call(node.querySelectorAll("input[type=radio], input[type=checkbox]"));
    for (var j = 0; j < inputs.length; j++) {
      var inp = inputs[j], label = inp.labels && inp.labels[0] ? inp.labels[0].textContent : "";
      if (same(inp.value) || same(label)) { if (!inp.checked || inp.type === "checkbox") inp.click(); return; }
    }
    node.click();
  }
  function chosen(node, value) {
    var want = String(value).trim().toLowerCase();
    if (node.tagName === "SELECT") {
      var o = node.options[node.selectedIndex];
      return !!o && (o.value.trim().toLowerCase() === want || o.textContent.trim().toLowerCase() === want);
    }
    var inputs = node.matches("input") ? [node] : Array.prototype.slice.call(node.querySelectorAll("input"));
    return inputs.some(function (i) {
      var label = i.labels && i.labels[0] ? i.labels[0].textContent.trim().toLowerCase() : "";
      return i.checked && (i.value.trim().toLowerCase() === want || label === want);
    });
  }
  /* Performs the action at once (guide mode's Next, "Do it for me"). */
  function actNow(step) {
    var a = step.action;
    if (!a || a.kind === "wait") return;
    var node = find(step, a.target);
    if (!node) return;
    if (a.kind === "click") clickKeepingFocus(node);
    else if (a.kind === "type") { setValue(node, a.value); fire(node, "change"); }
    else choose(node, a.value);
  }
  /* Play mode: the cursor glides to the element, then clicks, types or chooses; done() continues the step. */
  function actPlayed(step, done) {
    var a = step.action, node = find(step, a.target);
    if (!node) { done(); return; }
    moveCursor(node, !calm());
    wait(GLIDE, function () {
      if (a.kind === "click") {
        tap();
        wait(TAP, function () { clickKeepingFocus(node); done(); });
      } else if (a.kind === "choose") {
        tap();
        wait(TAP, function () { choose(node, a.value); done(); });
      } else {
        var letters = Array.from ? Array.from(a.value) : a.value.split("");
        var i = 0;
        node.classList.add("pl-typing");
        setValue(node, "");
        (function next() {
          if (i >= letters.length) { node.classList.remove("pl-typing"); fire(node, "change"); done(); return; }
          i += 1;
          setValue(node, letters.slice(0, i).join(""));
          wait(LETTER, next);
        })();
      }
    });
  }
  /* A click the player makes may navigate, and the shell then focuses the screen's title: when the viewer was working
     the dock (Enter on Next, Space on Pause), focus goes back to the dock so the next key still drives the tour. */
  function clickKeepingFocus(node) {
    var had = inChrome(document.activeElement);
    node.click();
    if (had && T.tour && !inChrome(document.activeElement)) focusPrimary();
  }
  function tap() {
    cursor.classList.remove("pl-tap");
    void cursor.offsetWidth;
    cursor.classList.add("pl-tap");
    setTimeout(function () { cursor.classList.remove("pl-tap"); }, 420);
  }

  /* ------------------------------------------------------------ your turn (guide mode) */
  function showHint(step, node) {
    var a = step.action, what = describe(node);
    var where = step.point === "cursor" ? ", where the cursor points" : step.point === "none" ? ""
      : ", highlighted on the screen";
    var text = step.hint || ("Not that one. " + (a.kind === "click" ? "Click " + what
      : a.kind === "type" ? "Type “" + a.value + "” into " + what
      : "Choose “" + a.value + "” in " + what) + where + ".");
    hint.textContent = text;
    hint.hidden = false;
    if (dock.hidden && T.tour) {
      /* the panel is hidden: bring it back for this step (the choice stays), and say the hint */
      var had = inChrome(document.activeElement);
      T.reveal = true;
      showPanel();
      if (had && focusLost()) focusPrimary();
      live.textContent = text;
    }
    layer.classList.remove("pl-flash");
    void layer.offsetWidth;
    layer.classList.add("pl-flash");
    if (node) {
      /* the real control blinks too, whatever the step points with */
      node.classList.remove("pl-attn");
      void node.offsetWidth;
      node.classList.add("pl-attn");
      setTimeout(function () { node.classList.remove("pl-attn"); }, 1200);
    }
    if (!cursor.hidden) tap();
  }
  function armTurn(step) {
    var a = step.action, run = T.run, done = false;
    function finish() {
      if (done) return;
      done = true;
      setTimeout(function () { if (run === T.run) advance(run); }, a.kind === "click" ? 60 : 350);
    }
    function onClick(e) {
      if (!frame.contains(e.target)) return;
      var node = find(step, a.target);
      var hit = node && (e.target === node || node.contains(e.target) ||
        (e.target.closest && e.target.closest("label") && e.target.closest("label").contains(node)));
      if (hit) { if (a.kind === "click") finish(); return; }
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      showHint(step, node);
    }
    function onInput(e) {
      var node = find(step, a.target);
      if (!node || !(e.target === node || node.contains(e.target))) return;
      if (a.kind === "type") {
        var v = (node.value !== undefined ? node.value : node.textContent) || "";
        if (v.replace(/\s+/g, " ").trim().toLowerCase() === a.value.replace(/\s+/g, " ").trim().toLowerCase()) finish();
      } else if (a.kind === "choose" && chosen(node, a.value)) finish();
    }
    window.addEventListener("click", onClick, true);
    document.addEventListener("input", onInput, true);
    document.addEventListener("change", onInput, true);
    T.turn = function () {
      window.removeEventListener("click", onClick, true);
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("change", onInput, true);
    };
  }

  /* ------------------------------------------------------------ rendering one item of the sequence */
  function itemTitle(item) { return item.kind === "card" ? item.title : (item.step.title || "Step " + item.step.n); }
  function writeHash() {
    var item = T.seq[T.pos], n = null;
    if (item.kind === "step") n = item.step.n;
    else if (item.card === "chapter") n = T.tour.steps[T.tour.chapters[item.chapter].first].n;
    else if (item.card === "closing") n = T.tour.steps.length;
    var hash = "#tour-" + T.tour.id + (n ? "-" + n : "");
    if (decodeURIComponent(location.hash) === hash) return;
    try { history.replaceState(null, "", location.href.split("#")[0] + hash); } catch (err) { /* file: in some browsers */ }
  }
  function announce(item) {
    var text;
    if (item.kind === "card") {
      text = (item.card === "intro" ? "Introduction: " : item.card === "closing" ? "Closing: " : "Chapter: ") + item.title +
        (item.text ? ". " + item.text : "");
    } else {
      var s = item.step;
      text = "Step " + s.n + " of " + T.tour.steps.length + ": " + itemTitle(item) + "." + (s.caption ? " " + s.caption : "") +
        (s.callout ? " " + s.callout.text : "") + (s.note ? " " + s.note.text : "") +
        (s.yourTurn && T.mode === "guide" ? " Your turn: do it in the prototype." : "");
    }
    live.textContent = text;
  }
  function paintDock() {
    var item = T.seq[T.pos], last = T.pos === T.seq.length - 1, guide = T.mode === "guide";
    var count;
    if (item.kind === "step") {
      count = "Step " + item.step.n + " of " + T.tour.steps.length;
      if (item.step.chapter !== null && T.tour.chapters[item.step.chapter]) count += " · " + T.tour.chapters[item.step.chapter].title;
    } else if (item.card === "chapter") count = "Chapter " + (item.chapter + 1) + " of " + T.tour.chapters.length;
    else count = item.card === "intro" ? "Introduction" : "Closing";
    eyebrow.textContent = (guide ? "Guide" : "Play") + " · " + T.tour.title + " · " + count;
    dock.setAttribute("aria-label", "Walkthrough: " + T.tour.title);
    dTitle.textContent = itemTitle(item);
    pillTitle.textContent = guide ? itemTitle(item) : "";
    pillTitle.hidden = !guide;
    pillDo.hidden = !(guide && item.kind === "step" && item.step.yourTurn);
    hideBtn.hidden = T.ended;
    dCaption.textContent = item.kind === "card" ? (item.text || "") : (item.step.caption || "");
    var turn = guide && item.kind === "step" && item.step.yourTurn;
    navGroup.hidden = !guide;
    backBtn.disabled = T.pos === 0;
    nextBtn.hidden = turn;
    nextBtn.textContent = last ? "Finish" : "Next";
    doBtn.hidden = !turn;
    playGroup.hidden = guide;
    playBtn.textContent = T.ended ? "Play again" : T.paused ? "Play" : "Pause";
    speedBtns.forEach(function (b) { b.setAttribute("aria-pressed", String(parseFloat(b.getAttribute("data-speed")) === T.speed)); });
    modeBtn.textContent = guide ? "Play from here" : "Guide me from here";
    var current = -1;
    T.scenes.forEach(function (sc, i) { if (sc.pos <= T.pos) current = i; });
    marks.forEach(function (m, i) { if (i === current) m.setAttribute("aria-current", "step"); else m.removeAttribute("aria-current"); });
    badge.hidden = guide || T.ended;
    badge.textContent = (T.paused ? "❚❚ Paused" : "▶ Playing") + " · " + times(T.speed);
    paintProgress();
  }
  function paintProgress() {
    if (!T.tour) return;
    var len = T.seq.length, part = 1;
    if (T.mode === "play" && !T.ended) {
      var w = T.wait, used = T.spent;
      if (w) used += w.total - (w.at === null ? w.left : Math.max(0, w.left - (now() - w.at) * w.rate));
      part = calm() ? 0 : clamp(used / Math.max(1, T.plan), 0, 1);
    }
    fill.style.width = ((T.pos + part) / len * 100).toFixed(2) + "%";
  }
  function tick() {
    paintProgress();
    T.raf = T.tour && T.mode === "play" && !T.paused ? requestAnimationFrame(tick) : 0;
  }
  function planOf(item) {
    if (item.kind === "card") return item.hold !== null && item.hold !== undefined ? item.hold : CARD_HOLD;
    var s = item.step, a = s.action, hold = s.hold !== null ? s.hold : STEP_HOLD;
    if (!a) return hold;
    if (a.kind === "click") return hold + GLIDE + TAP + AFTER;
    if (a.kind === "type") return LEAD + GLIDE + LETTER * a.value.length + hold;
    if (a.kind === "choose") return LEAD + GLIDE + TAP + hold;
    return hold + a.ms;
  }
  function render(pos, opts) {
    opts = opts || {};
    T.run += 1;
    stopTimers();
    clearStep();
    T.pos = clamp(pos, 0, T.seq.length - 1);
    T.ended = false;
    T.spent = 0;
    T.reveal = false;
    if (T.panelHidden && !dock.hidden) showPanel();  /* back to the viewer's choice after a hint or the end of play */
    var item = T.seq[T.pos];
    T.plan = planOf(item);
    if (item.kind === "step") api.go(item.step.screen, item.step.state, { history: null });
    writeHash();
    paintDock();
    if (item.kind === "card") {
      cursor.hidden = true;
      cardEyebrow.textContent = item.card === "intro" ? "Walkthrough" : item.card === "closing" ? "What next" :
        "Chapter " + (item.chapter + 1);
      cardTitle.textContent = item.title;
      cardText.textContent = item.text || "";
      cardText.hidden = !item.text;
      cardLink.hidden = !(appView && item.card === "closing");
      if (!cardLink.hidden) {
        var cur = api.current(), info = cur.screen ? screenInfo(cur.screen) : null;
        cardLink.setAttribute("href", "prototype.html" + (info ? "#screen-" + encodeURIComponent(cur.screen) +
          (cur.state && cur.state !== info.states[0] ? "/" + encodeURIComponent(cur.state) : "") : ""));
      }
      card.hidden = false;
      placeCard();
    } else {
      var s = item.step;
      if (T.mode !== "play" && s.point !== "cursor") cursor.hidden = true;
      decorate(s);
      if (T.mode === "play") { subtitle.textContent = s.caption || itemTitle(item); subtitle.hidden = false; placeSubtitle(); }
      else if (s.yourTurn) armTurn(s);
      else if (s.action && (s.action.kind === "type" || s.action.kind === "choose")) actNow(s);
    }
    announce(item);
    var active = document.activeElement;
    if (opts.focus || (inChrome(active) && (active.hidden || active.disabled || !active.getClientRects().length))) focusPrimary();
    emit();
    if (T.mode === "play" && !T.paused) { playItem(item); if (!T.raf && !calm()) T.raf = requestAnimationFrame(tick); }
  }
  function playItem(item) {
    var run = T.run;
    function next() { advance(run); }
    if (item.kind === "card") { wait(planOf(item), next); return; }
    var s = item.step, a = s.action, hold = s.hold !== null ? s.hold : STEP_HOLD;
    if (!a) wait(hold, next);
    else if (a.kind === "click") wait(hold, function () { actPlayed(s, function () { wait(AFTER, next); }); });
    else if (a.kind === "wait") wait(hold + a.ms, next);
    else wait(LEAD, function () { actPlayed(s, function () { wait(hold, next); }); });
  }
  function advance(run) {
    if (run !== T.run || !T.tour) return;
    if (T.pos + 1 < T.seq.length) render(T.pos + 1);
    else if (T.mode === "play") end();
    else leave("The walkthrough is finished.");
  }
  function end() {
    T.run += 1;
    stopTimers();
    T.ended = true;
    T.paused = true;
    subtitle.hidden = true;
    paintDock();
    var had = inChrome(document.activeElement);
    showPanel();  /* Play again and Leave are in the panel: it comes back at the end, the choice stays */
    if (had && focusLost()) focusPrimary();
    fill.style.width = "100%";
    live.textContent = "Played to the end. Press Play again to watch it again, or Leave to look around.";
    emit();
  }
  function focusPrimary() {
    var target = dock.hidden && !pill.hidden ? showBtn : T.mode === "play" ? playBtn : (!nextBtn.hidden ? nextBtn : doBtn);
    try { target.focus({ preventScroll: true }); } catch (err) { target.focus(); }
  }

  /* ------------------------------------------------------------ commands */
  function start(id, opts) {
    opts = opts || {};
    var tour = byId[id];
    if (!tour) return false;
    var wasActive = !!T.tour;
    T.run += 1;
    stopTimers();
    clearStep();
    if (!wasActive) {
      var a = document.activeElement;
      T.opener = opts.opener || (a && a !== document.body && !dock.contains(a) ? a : null);
    }
    T.tour = tour;
    T.mode = opts.mode === "play" || opts.mode === "guide" ? opts.mode : tour.mode;
    T.seq = sequence(tour);
    T.scenes = scenesOf(tour, T.seq);
    T.speed = SPEEDS.indexOf(opts.speed) >= 0 ? opts.speed : tour.speed;
    T.paused = false;
    T.ended = false;
    var pos = 0;
    if (typeof opts.pos === "number") pos = opts.pos;
    else if (opts.step) {
      for (var i = 0; i < T.seq.length; i++) if (T.seq[i].kind === "step" && T.seq[i].step.n === opts.step) { pos = i; break; }
    }
    markBox.textContent = "";
    marks = T.scenes.map(function (sc, k) {
      var b = button("", "", { "aria-label": "Scene " + (k + 1) + " of " + T.scenes.length + ": " + sc.label, title: sc.label });
      b.style.left = (sc.pos / T.seq.length * 100).toFixed(2) + "%";
      b.addEventListener("click", function () { jump(sc.pos); });
      markBox.appendChild(b);
      return b;
    });
    skip.hidden = false;
    document.body.classList.add("pl-docked", "pl-touring");
    showPanel();
    if (!wasActive) note("Started the walkthrough “" + tour.title + "”");
    render(pos, { focus: opts.focus !== false });
    return true;
  }
  function leave(message) {
    if (!T.tour) return;
    T.run += 1;
    stopTimers();
    clearStep();
    cursor.hidden = true;
    badge.hidden = true;
    dock.hidden = true;
    pill.hidden = true;
    skip.hidden = true;
    document.body.classList.remove("pl-docked", "pl-touring");
    if (T.raf) cancelAnimationFrame(T.raf);
    T.raf = 0;
    var title = T.tour.title;
    T.tour = null; T.mode = null; T.seq = []; T.scenes = []; T.paused = false; T.ended = false;
    var cur = api.current();
    if (cur.page === "screen" && cur.screen) {
      var info = screenInfo(cur.screen);
      var hash = (appView ? "#/" : "#screen-") + cur.screen + (info && cur.state !== info.states[0] ? "/" + cur.state : "");
      try { history.replaceState(null, "", location.href.split("#")[0] + hash); } catch (err) { /* ignore */ }
    }
    live.textContent = message || (appView ? "Left the walkthrough. The app is yours to click around."
      : "Left the walkthrough. The prototype is yours to click around.");
    note("Left the walkthrough “" + title + "”");
    emit();
    var back = T.opener;
    T.opener = null;
    if (back && document.contains(back) && back.getClientRects().length) back.focus({ preventScroll: true });
    else {
      /* the prototype's screen title; in the app view (no title) the screen on show */
      var h = $("pp-title") || (cur.screen ? api.screen(cur.screen) : null);
      if (h) {
        if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
        h.focus({ preventScroll: true });
      }
    }
  }
  function next() {
    if (!T.tour) return;
    var item = T.seq[T.pos];
    if (T.mode === "guide" && item.kind === "step") {
      if (item.step.yourTurn) { showHint(item.step, find(item.step, item.step.action.target)); return; }
      if (item.step.action && item.step.action.kind === "click") actNow(item.step);
    }
    if (T.pos + 1 < T.seq.length) render(T.pos + 1);
    else if (T.mode === "guide") leave("The walkthrough is finished.");
    else end();
  }
  function back() { if (T.tour && T.pos > 0) render(T.pos - 1); }
  function jump(pos) { if (T.tour) { if (T.ended) T.paused = false; render(pos); } }
  function setPaused(on) {
    if (!T.tour || T.mode !== "play") return;
    if (T.ended) { T.paused = false; render(0); return; }
    if (T.paused === on) return;
    T.paused = on;
    if (on) { freeze(); if (T.raf) cancelAnimationFrame(T.raf); T.raf = 0; }
    else {
      if (T.wait) arm(); else playItem(T.seq[T.pos]);
      if (!T.raf && !calm()) T.raf = requestAnimationFrame(tick);
    }
    paintDock();
    live.textContent = on ? "Paused." : "Playing.";
    emit();
  }
  function setSpeed(v) {
    v = parseFloat(v);
    if (SPEEDS.indexOf(v) < 0) return;
    if (T.wait && !T.paused) freeze();
    T.speed = v;
    if (T.tour && T.mode === "play" && !T.paused && T.wait) arm();
    if (T.tour) { paintDock(); emit(); }
  }
  function setMode(mode) {
    if (!T.tour || (mode !== "play" && mode !== "guide")) return;
    T.mode = mode;
    T.paused = false;
    render(T.pos, { focus: true });
  }
  /* The page keeps room at its bottom for the dock, or for the pill while the panel is hidden. */
  function sizeDock() {
    document.body.style.setProperty("--pl-dock-h", (dock.hidden ? pill.offsetHeight : dock.offsetHeight) + "px");
  }
  /* Shows the dock, or the pill in its place while the viewer keeps the panel hidden, and re-places what sits above
     them (subtitle, title card, labels). */
  function showPanel() {
    var hide = !!T.tour && T.panelHidden && !T.reveal && !T.ended;
    dock.hidden = !T.tour || hide;
    pill.hidden = !hide;
    sizeDock();
    if (T.step) placeChrome(T.step, null);  /* the pill is smaller than the dock: it may fit at the bottom */
    placeSubtitle();
    placeCard();
    if (T.redraw) T.redraw();
  }
  function setPanel(hide) {
    if (!T.tour || T.ended) return;  /* at the end of play the panel stays, with Play again */
    var had = inChrome(document.activeElement);
    T.reveal = false;
    T.panelHidden = !!hide;
    storeHidden(T.panelHidden);
    showPanel();
    if (had) {
      var to = T.panelHidden ? showBtn : hideBtn;
      try { to.focus({ preventScroll: true }); } catch (err) { to.focus(); }
    }
    live.textContent = T.panelHidden ? "Panel hidden. Press H or Show panel to bring it back." : "Panel shown.";
  }

  leaveBtn.addEventListener("click", function () { leave(); });
  hideBtn.addEventListener("click", function () { setPanel(true); });
  showBtn.addEventListener("click", function () { setPanel(false); });
  backBtn.addEventListener("click", back);
  nextBtn.addEventListener("click", next);
  function doItForMe() {
    var item = T.seq[T.pos];
    if (!item || item.kind !== "step") return;
    var run = T.run;
    actNow(item.step);
    setTimeout(function () { advance(run); }, 60);
  }
  doBtn.addEventListener("click", doItForMe);
  pillDo.addEventListener("click", doItForMe);
  playBtn.addEventListener("click", function () { setPaused(!T.paused); });
  restartBtn.addEventListener("click", function () { if (T.tour) { T.paused = false; render(0, { focus: true }); } });
  modeBtn.addEventListener("click", function () { setMode(T.mode === "guide" ? "play" : "guide"); });
  speedBtns.forEach(function (b) { b.addEventListener("click", function () { setSpeed(b.getAttribute("data-speed")); }); });

  document.addEventListener("keydown", function (e) {
    if (!T.tour || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
    var t = e.target;
    var typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || "") ||
      /^(textbox|combobox|searchbox|spinbutton)$/.test((t.getAttribute && t.getAttribute("role")) || ""));
    if (e.key === "Escape") { e.preventDefault(); leave(); return; }
    if (typing) return;
    if (e.key === "ArrowRight") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); back(); }
    else if ((e.key === "h" || e.key === "H") && !e.shiftKey) {
      e.preventDefault();
      if (!e.repeat) setPanel(!dock.hidden);  /* holding H toggles once */
    }
    else if ((e.key === " " || e.key === "Spacebar") && T.mode === "play") {
      if (t && t.closest && t.closest("button, a[href], [role=button], summary")) return;
      e.preventDefault();
      setPaused(!T.paused);
    }
  });
  window.addEventListener("resize", function () {
    if (T.step) placeChrome(T.step, null);
    if (T.redraw) T.redraw();
    if (T.tour) { sizeDock(); placeSubtitle(); placeCard(); }
  });
  window.addEventListener("scroll", function () { if (T.tour) { placeSubtitle(); placeCard(); } }, { passive: true });
  /* The marks follow the viewer's own scrolling inside the screen (a list, a table, a scrolling main): redrawn once a
     frame while something in the frame scrolls; a redraw measures and never scrolls. */
  var scrollRedraw = 0;
  document.addEventListener("scroll", function (e) {
    var n = e.target;
    if (!T.redraw || scrollRedraw || !n || n.nodeType !== 1 || !frame.contains(n)) return;
    scrollRedraw = requestAnimationFrame(function () { scrollRedraw = 0; if (T.redraw) T.redraw(); });
  }, { capture: true, passive: true });
  if (window.ResizeObserver) {
    new ResizeObserver(function () { if (T.redraw) T.redraw(); }).observe(frame);
    var chromeSized = new ResizeObserver(function () { if (T.tour) { sizeDock(); placeSubtitle(); placeCard(); } });
    chromeSized.observe(dock);
    chromeSized.observe(pill);
  }

  /* ------------------------------------------------------------ links: #tour-<id> and #tour-<id>-<n> */
  function fromHash(hash) {
    var h;
    try { h = decodeURIComponent(String(hash || "").replace(/^#/, "")); } catch (err) { h = String(hash || "").replace(/^#/, ""); }
    if (h.indexOf("tour-") !== 0) return false;
    var rest = h.slice(5);
    if (byId[rest]) return start(rest, {});
    var m = /^(.*)-(\d+)$/.exec(rest);
    if (m && byId[m[1]]) return start(m[1], { step: parseInt(m[2], 10) });
    return false;
  }
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var link = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    var href = link ? link.getAttribute("href") : "";
    if (!href || href.indexOf("#tour-") !== 0) return;
    e.preventDefault();
    if (fromHash(href)) {
      try { history.pushState(null, "", location.href.split("#")[0] + href); } catch (err) { /* ignore */ }
      writeHash();
    }
  }, true);
  window.addEventListener("hashchange", function () { fromHash(location.hash); });

  /* ------------------------------------------------------------ the per-screen guide panel */
  var guide = api.guide;
  var gTitle, gPurpose, gDo, gTry, gFeed, gFeedEmpty;
  function note(text) {
    if (!gFeed) return;
    gFeedEmpty.hidden = true;
    gFeed.insertBefore(el("li", null, text), gFeed.firstChild);
    while (gFeed.children.length > 8) gFeed.removeChild(gFeed.lastChild);
  }
  function section(body, heading) {
    var s = el("section");
    s.appendChild(el("h3", null, heading));
    body.appendChild(s);
    return s;
  }
  function launch(btn, id, opts) {
    btn.addEventListener("click", function () { opts.opener = btn; start(id, opts); });
  }
  function buildGuide() {
    if (!guide) return;
    guide.textContent = "";
    guide.hidden = false;
    var top = el("div", "pl-guide-top");
    top.appendChild(el("h2", null, "Guide"));
    var toggle = button("pp-btn", "Hide", { "aria-expanded": "true", "aria-controls": "pl-guide-body" });
    top.appendChild(toggle);
    var body = el("div", "pl-guide-body", null, { id: "pl-guide-body" });
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Hide" : "Show";
      body.hidden = !open;
    });
    guide.appendChild(top);
    guide.appendChild(body);
    var s1 = section(body, "This screen");
    gTitle = el("p", "pl-gs-title"); gPurpose = el("p", "pl-gs-purpose");
    s1.appendChild(gTitle); s1.appendChild(gPurpose);
    gDo = el("ul", "pl-gs-do", null, { role: "list" });
    section(body, "What you can do").appendChild(gDo);
    gTry = el("div", "pl-gs-try");
    section(body, "Try it").appendChild(gTry);
    var s4 = section(body, "Walkthroughs");
    if (!tours.length) {
      s4.appendChild(el("p", "empty", "No walkthroughs yet. /plumb:prototype writes one for each flow it builds; /plumb:tour writes custom ones."));
    } else {
      var list = el("ul", "pl-tours", null, { role: "list" });
      tours.forEach(function (t) {
        var li = el("li");
        li.appendChild(el("p", "pl-gs-title", t.title));
        li.appendChild(el("p", "pl-tour-meta", t.steps.length + " step" + (t.steps.length === 1 ? "" : "s") + " · for " +
          t.audience.replace("-", " ") + " · opens in " + t.mode + " mode"));
        var group = el("div", "pl-group");
        var g = button("pl-btn" + (t.mode === "guide" ? " pl-primary" : ""), "Guide me", { "data-tour-start": t.id, "data-mode": "guide",
          "aria-label": "Guide me through " + t.title });
        var p = button("pl-btn" + (t.mode === "play" ? " pl-primary" : ""), "Play", { "data-tour-start": t.id, "data-mode": "play",
          "aria-label": "Play " + t.title });
        launch(g, t.id, { mode: "guide" });
        launch(p, t.id, { mode: "play" });
        group.appendChild(g); group.appendChild(p);
        li.appendChild(group);
        list.appendChild(li);
      });
      s4.appendChild(list);
    }
    var s5 = section(body, "What just happened");
    gFeed = el("ol", "pl-feed", null, { role: "list" });
    gFeedEmpty = el("p", "empty", "Nothing yet: open a screen, change its state or start a walkthrough.");
    s5.appendChild(gFeed); s5.appendChild(gFeedEmpty);
  }
  function flash(node) {
    if (T.tour || !node) return;
    clearOverlays();
    scrollToNode(shape(node) || node, { block: "nearest" });
    ring("pl-ring", box(node));
    setTimeout(function () { if (!T.tour) clearOverlays(); }, 1600);
  }
  function updateGuide(cur) {
    if (!guide || !gTitle || cur.page !== "screen" || !cur.screen) return;
    var info = screenInfo(cur.screen), sec = api.screen(cur.screen);
    gTitle.textContent = info ? info.title + (info.states.length > 1 ? " · " + stateLabel(cur.state) : "") : cur.screen;
    var purpose = sec ? (sec.getAttribute("data-purpose") || "").trim() : "";
    gPurpose.textContent = purpose;
    gPurpose.hidden = !purpose;
    gDo.textContent = "";
    var seen = {};
    if (sec) {
      Array.prototype.forEach.call(sec.querySelectorAll("[data-guide]"), function (n) {
        var text = (n.getAttribute("data-guide") || "").trim();
        if (!text || seen[text] || !n.getClientRects().length) return;
        seen[text] = true;
        /* "F01 · what changed and why": a change id (a letter and digits, then ·) shows as a chip */
        var id = /^([A-Za-z]\d+)\s*·\s*([\s\S]*)$/.exec(text), li = el("li"), b = button("", id ? null : text);
        if (id) {
          b.appendChild(el("span", "pl-chip", id[1], { "data-change": id[1] }));
          b.appendChild(document.createTextNode(id[2]));
        }
        b.addEventListener("click", function () { flash(n); });
        li.appendChild(b);
        gDo.appendChild(li);
      });
    }
    gTry.textContent = "";
    tours.forEach(function (t) {
      var first = null;
      t.steps.forEach(function (s) {
        if (s.screen !== cur.screen) return;
        if (first === null) first = s.n;
        var text = s.title || s.caption;
        if (seen[text]) return;
        seen[text] = true;
        var li = el("li"), b = button("", null);
        b.appendChild(document.createTextNode(text));
        b.appendChild(el("span", "pl-from", "Step " + s.n + " of “" + t.title + "”"));
        b.addEventListener("click", function () { start(t.id, { mode: "guide", step: s.n, opener: b }); });
        li.appendChild(b);
        gDo.appendChild(li);
      });
      if (first !== null) {
        var tb = button("pl-btn", "Try it: " + t.title, { "data-try": t.id });
        tb.addEventListener("click", function () { start(t.id, { mode: "guide", step: first, opener: tb }); });
        gTry.appendChild(tb);
      }
    });
    if (!gDo.children.length) {
      gDo.appendChild(el("li", "empty", "Nothing listed for this screen yet: mark a control with data-guide=\"...\" in the screen file, or add a walkthrough step here."));
    }
    if (!gTry.children.length) gTry.appendChild(el("p", "empty", "No walkthrough visits this screen yet."));
  }
  var last = api.current();
  api.on(function (cur) {
    if (cur.page === "decisions") note("Opened Decisions");
    else if (cur.screen !== last.screen || last.page !== "screen") {
      var info = screenInfo(cur.screen);
      note("Opened " + (info ? info.title : cur.screen) + (info && cur.state !== info.states[0] ? " (" + stateLabel(cur.state) + ")" : ""));
    } else if (cur.state !== last.state) {
      var i2 = screenInfo(cur.screen);
      note((i2 ? i2.title : cur.screen) + ": " + stateLabel(cur.state));
    }
    last = cur;
    updateGuide(cur);
    if (T.redraw) T.redraw();
  });
  buildGuide();
  updateGuide(api.current());

  window.plumbPlayer = {
    tours: tours.map(function (t) { return t.id; }),
    start: function (id, opts) { return start(id, opts || {}); },
    leave: function () { leave(); },
    next: next,
    back: back,
    jump: jump,
    pause: function () { setPaused(true); },
    resume: function () { setPaused(false); },
    setSpeed: setSpeed,
    setMode: setMode,
    state: state
  };
  if (!fromHash(location.hash) && config.autostart && byId[config.autostart.tour]) {
    /* no focus move on load: nobody asked for it; the first Tab lands on "Skip to the walkthrough" */
    start(config.autostart.tour, { mode: config.autostart.mode, focus: false });
  }
})();
