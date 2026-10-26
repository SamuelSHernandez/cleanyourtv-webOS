/*
 * The launcher page: renders Home from the model, routes keys and pointer events, and talks to the platform only
 * through CYTV.adapter (adapter-webos.js on a TV, preview-adapter.js in the local preview).
 *
 * Home follows the Android launcher: a top bar (top_bar_apps, Inputs, Settings), then one ordered list of tiles
 * whose first row is the dock. Holding OK on a tile opens its menu; holding OK on Settings opens the launcher
 * menu (Launcher settings, Reorder apps, App library). All text comes from the shared strings (strings.js).
 *
 * DOM is rebuilt only when the model or the config changes; a focus move swaps class names. While the page is
 * hidden nothing runs: every timer stops, a held OK is forgotten, menus close and reordering ends.
 */
(function (root) {
  'use strict';

  var C = root.CYTV;
  var doc = root.document;
  var adapter = C.adapter;
  var theme = C.theme && typeof C.theme === 'object' ? C.theme : { name: '', hash: '', config: null, wallpapers: null };
  var perf = root.performance && root.performance.now ? root.performance : { now: function () { return Date.now(); } };
  var metrics = C.metrics = { scriptStart: perf.now(), ready: null, lastBuildMs: null, builds: 0, lastKeyToFocusMs: null };

  var GAP = 26;
  var ROW_GAP = 64;      // launcher.css .row margin-bottom: the name line under a tile
  var HOME_WIDTH = 1728;
  var COLUMN_CHOICES = [3, 4, 5, 6, 7, 8];
  var CLOCK_CHOICES = [0, 5, 15, 30, 60];
  var SVG = 'http://www.w3.org/2000/svg';

  function $(id) { return doc.getElementById(id); }
  var el = {
    body: doc.body, root: $('root'), sky: $('sky'), wallpaper: $('wallpaper'), dim: $('wallpaper-dim'),
    greeting: $('greeting'), clock: $('clock'), date: $('date'), shamsi: $('shamsi'), lunar: $('lunar'),
    topbar: $('topbar'), caption: $('caption'), spacer: $('spacer'), dockTitle: $('dock-title'), home: $('home'),
    notice: $('notice'), menu: $('menu'), menuTitle: $('menu-title'), menuHint: $('menu-hint'), menuItems: $('menu-items'),
    saver: $('screensaver'), ssWallpaper: $('ss-wallpaper'), ssDim: $('ss-dim'), ssGlow: $('ss-glow'), ssTime: $('ss-time')
  };

  var store = new C.prefs.Store(safeStorage());
  var refresh = new C.refresh.Refresh();
  var cardFeature = new C.cards.Feature(function (e) { setProblem('cards', 'Module cards switched off: ' + e.message); });
  var cfg;
  var strings;
  var caps = { shortcuts: {} };
  var apps = [];
  var view = { tiles: [], dockSize: 0, top: [], library: [] };
  var sections = [];          // for nav: { id, count, columns }
  var items = [];             // items[section][index] -> { el, kind, ... }
  var focus = null;
  var menus = [];             // the open panel stack; the last one is shown
  var reorder = null;         // null, or { picked: index into the ordered ids or null }
  var problems = {};
  var timers = { clock: null, wallpaper: null, idle: null, flash: null };
  var currentWallpaper = null;
  var captionMap = C.wallpaper.captions(theme.wallpapers ? theme.wallpapers.captions : '');
  var visible = !doc.hidden;
  var appKeyMap = {};

  var keys = new C.keys.Keys({
    move: onMove, activate: onActivate, hold: onHold, back: onBack
  }, {
    set: function (fn, ms) { return root.setTimeout(fn, ms); },
    clear: function (h) { root.clearTimeout(h); },
    now: function () { return Date.now(); }
  });

  function safeStorage() {
    try { return root.localStorage; } catch (e) { return null; }
  }

  function t() { return strings.t.apply(strings, arguments); }

  function addClass(node, name) {
    if ((' ' + node.className + ' ').indexOf(' ' + name + ' ') < 0) node.className = (node.className ? node.className + ' ' : '') + name;
  }
  function removeClass(node, name) {
    node.className = (' ' + node.className + ' ').replace(' ' + name + ' ', ' ').replace(/^ +| +$/g, '');
  }
  function setClass(node, name, on) { if (on) addClass(node, name); else removeClass(node, name); }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function show(node, on) { node.hidden = !on; }

  // ---- config ---------------------------------------------------------------------------------------------

  function resolveConfig() {
    var r = C.config.resolve(theme.config, store.prefs.overrides);
    cfg = r.config;
    var lang = cfg.locale || (root.navigator && root.navigator.language) || 'en';
    strings = new C.strings.Strings(C.STRINGS, lang);
    doc.documentElement.setAttribute('lang', strings.lang);
    appKeyMap = C.config.keyMap(cfg.app_keys);
    setProblem('theme', r.ignored.length ? 'Theme keys ignored: ' + r.ignored.join(', ') : null);
  }

  function applyConfig() {
    var b = el.body;
    b.style.background = cfg.background_color;
    b.className = '';
    addClass(b, 'glass-' + cfg.glass_style);
    addClass(b, !cfg.animations ? 'anim-off' : cfg.reduced_motion ? 'anim-reduced' : cfg.focus_overshoot ? 'anim-overshoot' : 'anim-plain');
    setClass(b, 'names-always', cfg.always_show_names);
    setClass(b, 'header-white', cfg.header_white);
    setClass(b, 'date-below', cfg.date_below_clock);
    show(el.greeting, cfg.show_greeting);
    show(el.shamsi, cfg.shamsi_date);
    show(el.lunar, cfg.lunar_date);
    show(el.dockTitle, cfg.dock_title && cfg.dock_row);
    el.dim.style.background = '#000000';
    el.dim.style.opacity = String(cfg.wallpaper_dim / 100);
    show(el.dim, cfg.wallpaper_dim > 0 && wallpaperOn());
    tickClock(false);
    startWallpaper();
  }

  // ---- notices --------------------------------------------------------------------------------------------

  function setProblem(key, text) {
    if (text) problems[key] = text; else delete problems[key];
    var lines = [];
    for (var k in problems) if (Object.prototype.hasOwnProperty.call(problems, k)) lines.push(problems[k]);
    el.notice.textContent = lines.join(' · ');
    show(el.notice, lines.length > 0);
    setClass(el.notice, 'hint', lines.length === 1 && !!problems.hint);
  }

  function flash(text) {
    if (!visible) return;   // an answer that arrives after the page was hidden starts no timer
    setProblem('flash', text);
    if (timers.flash) root.clearTimeout(timers.flash);
    timers.flash = root.setTimeout(function () { timers.flash = null; setProblem('flash', null); }, 5000);
  }

  // ---- header: clock, greeting, dates, sky ----------------------------------------------------------------

  function tickClock(schedule) {
    var now = new Date();
    el.clock.textContent = C.clock.time(now);
    el.date.textContent = C.clock.date(now, strings.lang);
    el.greeting.textContent = cfg.show_greeting ? C.clock.greeting(strings, now, cfg.greeting_name) : '';
    if (cfg.shamsi_date) el.shamsi.textContent = C.clock.shamsi(strings, now);
    if (cfg.lunar_date) el.lunar.textContent = C.clock.lunar(strings, now, cfg.lunar_utc_offset);
    if (cfg.sky_intensity > 0) {
      var c = C.clock.sky(now.getHours());
      el.sky.style.background = 'linear-gradient(to bottom, ' + c[0] + ', ' + c[1] + ')';
      el.sky.style.opacity = String(cfg.sky_intensity / 100);
      show(el.sky, true);
    } else {
      show(el.sky, false);
    }
    if (!el.saver.hidden) placeSaverClock(now);
    if (schedule !== false && visible) {
      if (timers.clock) root.clearTimeout(timers.clock);
      timers.clock = root.setTimeout(function () { timers.clock = null; tickClock(); }, (60 - now.getSeconds()) * 1000 + 50);
    }
  }

  // ---- wallpaper ------------------------------------------------------------------------------------------

  function wallpaperFiles() {
    var w = theme.wallpapers;
    return w && Array.isArray(w.files) ? w.files : [];
  }

  function hasWallpaper() {
    return !!(theme.wallpapers && (theme.wallpapers.single || wallpaperFiles().length));
  }

  function wallpaperOn() {
    return cfg.wallpaper && hasWallpaper();
  }

  function wallpaperSrc(name) {
    return name === theme.wallpapers.single ? 'theme/' + name : 'theme/wallpapers/' + name;
  }

  function startWallpaper() {
    if (timers.wallpaper) { root.clearTimeout(timers.wallpaper); timers.wallpaper = null; }
    if (!wallpaperOn()) {
      currentWallpaper = null;
      show(el.wallpaper, false);
      show(el.caption, false);
      return;
    }
    var files = wallpaperFiles();
    if (!files.length) {
      setWallpaper(theme.wallpapers.single);
      return;
    }
    var pool = C.wallpaper.pool(files, cfg.wallpaper_moods, new Date());
    if (!currentWallpaper || pool.indexOf(currentWallpaper) < 0) {
      setWallpaper(C.wallpaper.next(pool, null, cfg.wallpaper_order, Math.random));
    }
    if (cfg.wallpaper_rotation_minutes > 0 && visible) {
      timers.wallpaper = root.setTimeout(function () {
        timers.wallpaper = null;
        var p = C.wallpaper.pool(files, cfg.wallpaper_moods, new Date());
        setWallpaper(C.wallpaper.next(p, currentWallpaper, cfg.wallpaper_order, Math.random));
        startWallpaper();
      }, cfg.wallpaper_rotation_minutes * 60000);
    }
  }

  function setWallpaper(name) {
    currentWallpaper = name;
    if (!name) { show(el.wallpaper, false); return; }
    el.wallpaper.src = wallpaperSrc(name);
    show(el.wallpaper, true);
    var caption = cfg.wallpaper_captions ? captionMap[name] : null;
    el.caption.textContent = caption || '';
    show(el.caption, !!caption);
  }

  // ---- building Home ----------------------------------------------------------------------------------------

  function loadInventory(done) {
    adapter.listApps(function (err, list) {
      if (err) {
        setProblem('inventory', t('library_empty') + ': ' + err.message);
        refresh.invalidate();
      } else {
        setProblem('inventory', null);
        apps = list;
        refresh.built();
        rebuild();
      }
      if (done) done();
    });
  }

  function uiNames() {
    return [t('inputs'), t('settings'), t('live_tv'), t('app_library'), t('launcher_settings'), t('dream_name')];
  }

  function rebuild() {
    var started = perf.now();
    var keep = focusedKey();
    var cards = cardFeature.run(function () {
      return C.cards.approved(C.baked && C.baked.cards, uiNames());
    }, null);
    view = C.model.build(apps, cfg, store.prefs, cards, adapter.selfId, { reordering: !!reorder });
    items = [renderTopbar(), [], [], []];
    renderHome();
    var found = findKey(keep);
    setFocus(found || C.nav.clamp(sections, focus) || homeStart());
    setProblem('prefs', store.problem ? t('card_not_saved') + ' (' + store.problem + ')' : null);
    metrics.builds++;
    metrics.lastBuildMs = perf.now() - started;
  }

  function tileSize() {
    var w = Math.floor((HOME_WIDTH - (cfg.columns - 1) * GAP) / cfg.columns);
    return { w: w, h: Math.round(w * 9 / 16) };
  }

  function renderTopbar() {
    clear(el.topbar);
    var out = [];
    for (var i = 0; i < view.top.length; i++) {
      var a = view.top[i];
      var p = pill('', 'top:' + a.id, true);
      if (a.icon) p.appendChild(img(a.icon, 40));
      else p.appendChild(doc.createTextNode(a.title.charAt(0)));
      p.setAttribute('aria-label', a.title);
      out.push({ el: p, kind: 'app', id: a.id, title: a.title });
    }
    if (cfg.show_inputs_pill && (caps.shortcuts.inputs || caps.shortcuts.livetv)) {
      out.push({ el: pill(t('inputs'), 'pill:inputs', false), kind: 'inputs' });
    }
    var settings = pill(cfg.icon_only_buttons ? '' : t('settings'), 'pill:settings', cfg.icon_only_buttons);
    if (cfg.icon_only_buttons) {
      settings.appendChild(gear());
      settings.setAttribute('aria-label', t('settings'));
    }
    out.push({ el: settings, kind: 'settings' });
    for (var j = 0; j < out.length; j++) el.topbar.appendChild(out[j].el);
    return out;
  }

  function pill(label, key, round) {
    var b = doc.createElement('button');
    b.type = 'button';
    b.tabIndex = -1;
    b.className = 'pill' + (round ? ' round' : '');
    b.setAttribute('data-key', key);
    if (label) b.textContent = label;
    return b;
  }

  function img(src, size) {
    var i = doc.createElement('img');
    i.alt = '';
    i.src = src;
    i.style.width = size + 'px';
    i.style.height = size + 'px';
    i.onerror = function () { if (i.parentNode) i.parentNode.removeChild(i); };
    return i;
  }

  function gear() {
    var svg = doc.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    var c = doc.createElementNS(SVG, 'circle');
    c.setAttribute('cx', '12'); c.setAttribute('cy', '12'); c.setAttribute('r', '6.5');
    c.setAttribute('fill', 'none'); c.setAttribute('stroke', '#f2f4f7'); c.setAttribute('stroke-width', '3.5');
    c.setAttribute('stroke-dasharray', '3 2.1');
    var dot = doc.createElementNS(SVG, 'circle');
    dot.setAttribute('cx', '12'); dot.setAttribute('cy', '12'); dot.setAttribute('r', '2.6'); dot.setAttribute('fill', '#f2f4f7');
    svg.appendChild(c);
    svg.appendChild(dot);
    return svg;
  }

  function tileElement(tile, size) {
    var b = doc.createElement('button');
    b.type = 'button';
    b.tabIndex = -1;
    b.className = 'tile';
    b.setAttribute('data-key', 'tile:' + tile.id);
    b.style.width = size.w + 'px';
    b.style.height = size.h + 'px';
    if (tile.color) b.style.background = tile.color;
    var art = Math.min(Math.round(size.h * 0.58), 160);
    if (tile.icon) {
      var i = img(tile.icon, art);
      i.className = 'art';
      b.appendChild(i);
    } else {
      var l = doc.createElement('span');
      l.className = 'letter';
      l.textContent = tile.title.charAt(0).toUpperCase();
      b.appendChild(l);
    }
    var name = doc.createElement('span');
    name.className = 'name';
    name.textContent = tile.title;
    if (tile.card && tile.card.caption) {
      var cap = doc.createElement('span');
      cap.className = 'card-caption';
      cap.textContent = ' · ' + tile.card.caption;
      name.appendChild(cap);
    }
    b.appendChild(name);
    return b;
  }

  function renderHome() {
    clear(el.home);
    var size = tileSize();
    var cols = cfg.columns;
    var tiles = view.tiles;
    var dockSlots = cfg.dock_row ? Math.min(cols, tiles.length) : 0;
    var dockItems = [];
    var gridItems = [];
    if (dockSlots) {
      var band = doc.createElement('div');
      band.className = 'row dock' + (cfg.dock_band ? ' band' : ' bare') + (cfg.dock_band && cfg.dock_glass ? ' glass' : '');
      if (cfg.dock_band && !cfg.dock_glass) band.style.background = 'rgba(23, 26, 31, ' + (cfg.dock_opacity / 100) + ')';
      for (var d = 0; d < dockSlots; d++) {
        if (tiles[d]) {
          var te = tileElement(tiles[d], size);
          band.appendChild(te);
          dockItems.push({ el: te, kind: 'tile', tile: tiles[d] });
        } else {
          var slot = doc.createElement('div');
          slot.className = 'slot';
          slot.style.width = size.w + 'px';
          slot.style.height = size.h + 'px';
          band.appendChild(slot);
        }
      }
      el.home.appendChild(band);
    }
    var row = null;
    for (var g = dockSlots; g < tiles.length; g++) {
      if ((g - dockSlots) % cols === 0) {
        row = doc.createElement('div');
        row.className = 'row';
        el.home.appendChild(row);
      }
      if (!tiles[g]) continue;   // empty slots belong to the dock row only
      var ge = tileElement(tiles[g], size);
      row.appendChild(ge);
      gridItems.push({ el: ge, kind: 'tile', tile: tiles[g] });
    }
    var libItems = [];
    if (libraryOn()) {
      var lp = pill(t('app_library'), 'pill:library', false);
      addClass(lp, 'library-pill');
      el.home.appendChild(lp);
      libItems.push({ el: lp, kind: 'library' });
    }
    if (!tiles.length) {
      var empty = doc.createElement('p');
      empty.className = 'menu-hint';
      empty.textContent = t('library_empty');
      el.home.appendChild(empty);
    }
    // Push the dock down so that it, its name line and `rows_below_dock` grid rows end at the bottom of the
    // screen; rows beyond that are reached by scrolling, as upstream.
    var headerH = el.spacer.offsetTop || 190;   // the header's bottom inside #root, measured
    var titleH = cfg.dock_title && cfg.dock_row ? 76 : 0;
    var rowH = size.h + ROW_GAP;
    var dockH = cfg.dock_row ? size.h + 36 + ROW_GAP : 0;
    var libraryH = libItems.length && gridItems.length === 0 ? 132 : 0;   // keep the App library pill on screen
    var wanted = 1080 - headerH - titleH - dockH - libraryH - rowH * cfg.rows_below_dock;
    el.spacer.style.height = Math.max(0, Math.min(wanted, 520)) + 'px';
    items[1] = dockItems;
    items[2] = gridItems;
    items[3] = libItems;
    sections = [
      { id: 'top', count: items[0].length, columns: Math.max(1, items[0].length) },
      { id: 'dock', count: dockItems.length, columns: cols },
      { id: 'grid', count: gridItems.length, columns: cols },
      { id: 'library', count: libItems.length, columns: 1 }
    ];
  }

  // ---- focus ------------------------------------------------------------------------------------------------

  function itemAt(f) {
    return f && items[f.section] ? items[f.section][f.index] || null : null;
  }

  function focusedKey() {
    var it = itemAt(focus);
    return it ? it.el.getAttribute('data-key') : null;
  }

  function findKey(key) {
    if (!key) return null;
    for (var s = 0; s < items.length; s++) {
      for (var i = 0; i < items[s].length; i++) if (items[s][i].el.getAttribute('data-key') === key) return { section: s, index: i };
    }
    return null;
  }

  function homeStart() {
    if (sections[1] && sections[1].count) return { section: 1, index: 0 };
    if (sections[2] && sections[2].count) return { section: 2, index: 0 };
    return C.nav.first(sections);
  }

  function setFocus(next) {
    var old = itemAt(focus);
    if (old) {
      removeClass(old.el, 'focused');
      if (old.tile && old.tile.card && old.tile.card.accent) old.el.style.boxShadow = '';
    }
    focus = next;
    var it = itemAt(focus);
    if (!it) return;
    addClass(it.el, 'focused');
    if (it.tile && it.tile.card && it.tile.card.accent) it.el.style.boxShadow = '0 0 0 3px #000000, 0 0 0 7px ' + it.tile.card.accent + ', 0 0 40px ' + it.tile.card.accent;
    if (focus.section === 1 && it.tile) el.dockTitle.textContent = it.tile.title;
    keepVisible(it.el);
  }

  /** A node's top inside #root (offsetTop is relative to the nearest positioned ancestor, e.g. #home). */
  function topInRoot(node) {
    var y = 0;
    for (var n = node; n && n !== el.root; n = n.offsetParent) y += n.offsetTop;
    return y;
  }

  function keepVisible(node) {
    if (focus && focus.section === 0) { el.root.scrollTop = 0; return; }
    var top = topInRoot(node);
    var bottom = top + node.offsetHeight;
    var margin = 90;
    var height = el.root.clientHeight;
    if (bottom > el.root.scrollTop + height - margin) el.root.scrollTop = bottom - height + margin;
    else if (top < el.root.scrollTop + margin) el.root.scrollTop = Math.max(0, top - margin);
  }

  // ---- key handlers -----------------------------------------------------------------------------------------

  function onMove(dir) {
    var started = perf.now();
    if (menus.length) moveMenu(dir);
    else if (reorder && reorder.picked !== null) moveTile(dir);
    else {
      var next = C.nav.move(sections, focus, dir);
      if (next) setFocus(next);
    }
    metrics.lastKeyToFocusMs = perf.now() - started;
  }

  function onActivate() {
    if (menus.length) { runMenuItem(false); return; }
    if (reorder) {
      if (reorder.picked !== null) placeTile();
      else pickFocused();
      return;
    }
    activateFocused();
  }

  function onHold() {
    if (menus.length) { runMenuItem(true); return; }
    if (reorder) return;
    var it = itemAt(focus);
    if (!it) return;
    if (it.kind === 'tile') tileMenu(it.tile);
    else if (it.kind === 'settings') launcherMenu();
  }

  function onBack() {
    if (menus.length) { closeMenu(); return; }
    if (reorder) {
      if (reorder.picked !== null) placeTile();
      else endReorder();
    }
  }

  // ---- actions ----------------------------------------------------------------------------------------------

  function launch(id, title) {
    adapter.launch(id, function (err) { if (err) flash(t('cant_open', title) + ' (' + err.message + ')'); });
  }

  function openSettings() {
    adapter.openShortcut('settings', function (err) { if (err) flash(t('not_available')); });
  }

  function activateFocused() {
    var it = itemAt(focus);
    if (!it) return;
    if (it.kind === 'tile') launch(it.tile.id, it.tile.title);
    else if (it.kind === 'app') launch(it.id, it.title);
    else if (it.kind === 'inputs') inputsMenu();
    else if (it.kind === 'settings') openSettings();
    else if (it.kind === 'library') libraryMenu();
  }

  function runTarget(target) {
    if (target === 'inputs') inputsMenu();
    else if (target === 'settings') openSettings();
    else if (target === 'livetv') openLiveTv();
    else if (target === 'library') { if (libraryOn()) libraryMenu(); }
    else {
      for (var i = 0; i < apps.length; i++) if (apps[i].id === target) { launch(target, apps[i].title); return; }
      flash(t('not_available'));
    }
  }

  function openLiveTv() {
    var id = cfg.live_tv_package || adapter.inputs().liveTv;
    if (!id) { flash(t('not_available')); return; }
    launch(id, t('live_tv'));
  }

  function savePrefs(change, failure) {
    var saved;
    try {
      saved = store.update(change);
    } catch (e) {
      flash(failure || t('card_not_saved'));
      return false;
    }
    if (!saved) flash(failure || t('card_not_saved'));
    return true;
  }

  // ---- reorder (upstream's Move: OK picks up, arrows move, Back places; Back again finishes) ---------------

  function orderedIds() {
    return C.model.orderOf(view.tiles);
  }


  function focusId(id) {
    var found = findKey('tile:' + id);
    if (found) setFocus(found);
  }

  // The picked app is held by id: an inventory change during a reorder rebuilds Home, and an index would then
  // point at another app. Reorder mode shows no empty dock slots, as upstream's.
  function startReorder(tile) {
    closeAllMenus();
    reorder = { picked: null };
    setProblem('hint', t('reorder_hint'));
    rebuild();
    if (tile) { focusId(tile.id); pickFocused(); }
  }

  function pickFocused() {
    var it = itemAt(focus);
    if (!it || !it.tile) return;
    reorder.picked = it.tile.id;
    addClass(it.el, 'moving');
  }

  function moveTile(dir) {
    var ids = orderedIds();
    var from = ids.indexOf(reorder.picked);
    if (from < 0) { placeTile(); return; }   // the app left the TV while it was picked up
    var to = C.model.step(ids.length, cfg.columns, from, dir);
    if (to < 0) return;
    var moved = C.model.move(ids, from, to);
    if (!savePrefs(function (p) { p.order = moved; }, t('reorder_not_saved'))) return;
    rebuild();
    focusId(reorder.picked);
    var it = itemAt(focus);
    if (it) addClass(it.el, 'moving');
  }

  function placeTile() {
    var it = itemAt(focus);
    if (it) removeClass(it.el, 'moving');
    reorder.picked = null;
  }

  function endReorder() {
    if (!reorder) return;
    var it = itemAt(focus);
    if (it) removeClass(it.el, 'moving');
    reorder = null;
    setProblem('hint', null);
    rebuild();   // empty dock slots come back if no order was saved
  }

  // ---- menus and panels ---------------------------------------------------------------------------------------

  function openMenu(title, list, hintFor, kind) {
    menus.push({ title: title, items: list, index: 0, hintFor: hintFor || null, kind: kind || '' });
    drawMenu();
  }

  function drawMenu() {
    var m = menus[menus.length - 1];
    if (!m) { show(el.menu, false); return; }
    el.menuTitle.textContent = m.title;
    clear(el.menuItems);
    if (!m.items.length) {
      var p = doc.createElement('p');
      p.className = 'menu-hint';
      p.textContent = t('library_empty');
      el.menuItems.appendChild(p);
    }
    for (var i = 0; i < m.items.length; i++) {
      var b = doc.createElement('button');
      b.type = 'button';
      b.tabIndex = -1;
      b.className = 'item' + (i === m.index ? ' focused' : '');
      b.setAttribute('data-index', String(i));
      b.appendChild(doc.createTextNode(m.items[i].label));
      if (m.items[i].state) {
        var s = doc.createElement('span');
        s.className = 'state';
        s.textContent = m.items[i].state;
        b.appendChild(s);
      }
      el.menuItems.appendChild(b);
    }
    drawMenuHint();
    show(el.menu, true);
  }

  function drawMenuHint() {
    var m = menus[menus.length - 1];
    var hint = m && m.hintFor && m.items[m.index] ? m.hintFor(m.items[m.index]) : '';
    el.menuHint.textContent = hint || '';
  }

  function moveMenu(dir) {
    var m = menus[menus.length - 1];
    if (!m.items.length || (dir !== 'up' && dir !== 'down')) return;
    selectMenuItem(Math.max(0, Math.min(m.items.length - 1, m.index + (dir === 'down' ? 1 : -1))));
  }

  function selectMenuItem(i) {
    var m = menus[menus.length - 1];
    var nodes = el.menuItems.children;
    if (nodes[m.index]) removeClass(nodes[m.index], 'focused');
    m.index = i;
    if (nodes[i]) addClass(nodes[i], 'focused');
    drawMenuHint();
  }

  function runMenuItem(held) {
    var m = menus[menus.length - 1];
    var item = m.items[m.index];
    if (!item) return;
    var fn = held ? item.hold : item.run;
    if (!fn) return;
    if (!item.keepOpen && !held) closeAllMenus();
    fn();
  }

  function closeMenu() {
    menus.pop();
    drawMenu();
  }

  function closeAllMenus() {
    menus = [];
    show(el.menu, false);
  }

  function tileMenu(tile) {
    var list = [
      { label: t('library_open'), run: function () { launch(tile.id, tile.title); } },
      { label: t('tile_move'), run: function () { startReorder(tile); } }
    ];
    if (libraryOn()) list.push({ label: t('library_remove_shortcut'), run: function () { setOnHome(tile.id, false); } });
    list.push({ label: t('launcher_settings'), keepOpen: true, run: settingsPanel });
    openMenu(tile.title, list);
  }

  function launcherMenu() {
    var list = [
      { label: t('launcher_settings'), keepOpen: true, run: settingsPanel },
      { label: t('reorder'), run: function () { startReorder(null); } }
    ];
    if (libraryOn()) list.push({ label: t('app_library'), keepOpen: true, run: libraryMenu });
    if (caps.shortcuts.settings) list.push({ label: t('tv_settings'), run: openSettings });
    openMenu(t('launcher_settings'), list);
  }

  function onOff(v) { return v ? t('on') : t('off'); }

  function settingsItems() {
    var list = [
      { label: t('columns_label'), state: String(cfg.columns), keepOpen: true,
        run: function () { override('columns', cycle(COLUMN_CHOICES, cfg.columns)); } },
      { label: t('animations_state', onOff(cfg.animations)), keepOpen: true,
        run: function () { override('animations', !cfg.animations); } },
      { label: t('dream_name'), state: cfg.home_idle_clock_minutes ? t('race_countdown_minutes', cfg.home_idle_clock_minutes) : t('off'),
        keepOpen: true, run: function () { override('home_idle_clock_minutes', cycle(CLOCK_CHOICES, cfg.home_idle_clock_minutes)); } }
    ];
    if (hasWallpaper()) {
      list.push({ label: t('wallpaper_state', cfg.wallpaper ? t('wallpaper_theme_default') : t('wallpaper_none')), keepOpen: true,
        run: function () { override('wallpaper', !cfg.wallpaper); } });
    }
    list.push({ label: t('follow_theme'), keepOpen: true, run: function () {
      if (savePrefs(function (p) { p.overrides = {}; })) reconfigure();
    } });
    return list;
  }

  function settingsPanel() {
    openMenu(t('launcher_settings'), settingsItems(), null, 'settings');
  }

  function cycle(choices, value) {
    var at = choices.indexOf(value);
    return choices[(at + 1) % choices.length];
  }

  function override(key, value) {
    if (savePrefs(function (p) { p.overrides[key] = value; })) reconfigure();
  }

  /** The config changed on the TV: apply it, rebuild Home, and redraw the open settings panel in place. */
  function reconfigure() {
    resolveConfig();
    applyConfig();
    rebuild();
    resetIdle();
    var m = menus[menus.length - 1];
    if (m && m.kind === 'settings') {
      m.items = settingsItems();
      drawMenu();
    }
  }

  /** The App library is reachable: switched on, or implied by dock_only (the other apps live there). */
  function libraryOn() {
    return cfg.app_library || cfg.dock_only;
  }

  function setOnHome(id, on) {
    var configHidden = cfg.hidden_apps.indexOf(id) >= 0 || (cfg.dock_only && cfg.dock_apps.indexOf(id) < 0);
    savePrefs(function (p) {
      p.hidden = p.hidden.filter(function (x) { return x !== id; });
      p.shown = p.shown.filter(function (x) { return x !== id; });
      if (on && configHidden) p.shown.push(id);
      if (!on) p.hidden.push(id);
    });
    rebuild();
  }

  function libraryItems() {
    var list = [];
    for (var i = 0; i < view.library.length; i++) {
      (function (entry) {
        list.push({
          label: entry.tile.title,
          state: entry.onHome ? t('library_on_home') : '',
          onHome: entry.onHome,
          keepOpen: true,
          run: function () {
            if (entry.onHome) { closeAllMenus(); launch(entry.tile.id, entry.tile.title); return; }
            setOnHome(entry.tile.id, true);
            refreshLibrary();
          },
          hold: function () {
            var opts = [{ label: t('library_open'), run: function () { launch(entry.tile.id, entry.tile.title); } }];
            opts.push(entry.onHome
              ? { label: t('library_remove_shortcut'), run: function () { setOnHome(entry.tile.id, false); } }
              : { label: t('library_add_home'), run: function () { setOnHome(entry.tile.id, true); } });
            openMenu(entry.tile.title, opts);
          }
        });
      })(view.library[i]);
    }
    return list;
  }

  function libraryMenu() {
    openMenu(t('app_library'), libraryItems(), function (item) {
      return item.onHome ? t('library_hint_open') : t('library_hint_add');
    }, 'library');
  }

  function refreshLibrary() {
    var m = menus[menus.length - 1];
    if (!m || m.kind !== 'library') return;
    var index = m.index;
    m.items = libraryItems();
    m.index = Math.min(index, Math.max(0, m.items.length - 1));
    drawMenu();
  }

  function inputsMenu() {
    var info = adapter.inputs();
    var list = [];
    if (cfg.live_tv_package || info.liveTv) list.push({ label: t('live_tv'), run: openLiveTv });
    for (var i = 0; i < info.inputs.length; i++) {
      (function (x) { list.push({ label: x.label, run: function () { launch(x.app, x.label); } }); })(info.inputs[i]);
    }
    if (!list.length) {
      if (info.picker) adapter.openShortcut('inputs', function (err) { if (err) flash(t('no_inputs')); });
      else flash(t('no_inputs'));
      return;
    }
    openMenu(t('inputs'), list);
  }

  // ---- clock screensaver -------------------------------------------------------------------------------------

  function resetIdle() {
    if (timers.idle) { root.clearTimeout(timers.idle); timers.idle = null; }
    if (!visible || cfg.home_idle_clock_minutes <= 0) return;
    timers.idle = root.setTimeout(function () { timers.idle = null; showSaver(); }, cfg.home_idle_clock_minutes * 60000);
  }

  function showSaver() {
    if (!visible || menus.length || reorder) { resetIdle(); return; }
    var wall = cfg.clock_wallpaper && currentWallpaper;
    if (wall) el.ssWallpaper.src = wallpaperSrc(currentWallpaper);
    show(el.ssWallpaper, !!wall);
    el.ssDim.style.opacity = String(cfg.clock_wallpaper_dim / 100);
    show(el.ssDim, !!wall);
    show(el.ssGlow, cfg.clock_glow && !wall);
    show(el.saver, true);
    placeSaverClock(new Date());
  }

  function placeSaverClock(now) {
    clear(el.ssTime);
    el.ssTime.appendChild(doc.createTextNode(C.clock.time(now)));
    var d = doc.createElement('div');
    d.className = 'ss-date';
    d.textContent = C.clock.date(now, strings.lang);
    el.ssTime.appendChild(d);
    // A new place and colour every minute, so nothing stays lit in one spot (OLED).
    var x = Math.round(160 + Math.random() * 1200);
    var y = Math.round(120 + Math.random() * 640);
    el.ssTime.style.left = x + 'px';
    el.ssTime.style.top = y + 'px';
    var hue = (now.getHours() * 60 + now.getMinutes()) * 7 % 360;
    el.ssGlow.style.background = 'radial-gradient(circle at ' + x + 'px ' + y + 'px, hsla(' + hue +
      ', 70%, 45%, 0.6), rgba(0, 0, 0, 0) 60%)';
  }

  function hideSaver() {
    if (el.saver.hidden) return false;
    show(el.saver, false);
    resetIdle();
    return true;
  }

  // ---- pointer (Magic Remote) ---------------------------------------------------------------------------------

  function pointerTarget(e) {
    var node = e.target;
    while (node && node !== doc.body) {
      if (node.getAttribute && (node.getAttribute('data-key') || node.getAttribute('data-index') !== null)) return node;
      node = node.parentNode;
    }
    return null;
  }

  doc.addEventListener('mousemove', function () { if (!hideSaver()) resetIdle(); });

  doc.addEventListener('mouseover', function (e) {
    var node = pointerTarget(e);
    if (!node || reorder) return;
    if (menus.length) {
      var idx = node.getAttribute('data-index');
      if (idx !== null && +idx !== menus[menus.length - 1].index) selectMenuItem(+idx);
      return;
    }
    var found = findKey(node.getAttribute('data-key'));
    if (found && (!focus || found.section !== focus.section || found.index !== focus.index)) setFocus(found);
  });

  doc.addEventListener('click', function (e) {
    var node = pointerTarget(e);
    if (!node || !keys.click() || reorder) return;
    resetIdle();
    if (menus.length) {
      var idx = node.getAttribute('data-index');
      if (idx === null) return;
      selectMenuItem(+idx);   // the clicked item, even with no mouseover first
      runMenuItem(false);
      return;
    }
    var found = findKey(node.getAttribute('data-key'));
    if (found) { setFocus(found); activateFocused(); }
  });

  // ---- keys and lifecycle -------------------------------------------------------------------------------------

  doc.addEventListener('keydown', function (e) {
    if (hideSaver()) { e.preventDefault(); return; }   // the key that wakes Home does nothing else
    resetIdle();
    var mapped = !menus.length && !reorder ? appKeyMap[e.keyCode] : null;
    if (mapped) {
      e.preventDefault();
      if (!e.repeat) runTarget(mapped);
      return;
    }
    if (keys.keydown(e.keyCode, e.repeat)) e.preventDefault();
  });
  doc.addEventListener('keyup', function (e) {
    if (keys.keyup(e.keyCode)) e.preventDefault();
  });

  function stopTimers() {
    for (var k in timers) {
      if (Object.prototype.hasOwnProperty.call(timers, k) && timers[k]) { root.clearTimeout(timers[k]); timers[k] = null; }
    }
    setProblem('flash', null);
  }

  function onHidden() {
    visible = false;
    stopTimers();
    keys.reset();
    closeAllMenus();
    endReorder();
    show(el.saver, false);
    refresh.hidden();
  }

  function onShown() {
    visible = true;
    tickClock();
    startWallpaper();
    resetIdle();
    var action = refresh.shown();
    if (action === 'rebuild') loadInventory();
    else if (action === 'refocus') { setFocus(homeStart()); el.root.scrollTop = 0; }
  }

  doc.addEventListener('visibilitychange', function () {
    if (doc.hidden) onHidden(); else onShown();
  });
  // webOS sends webOSRelaunch when a running app is launched again, e.g. by a Home route: back to the dock.
  doc.addEventListener('webOSRelaunch', function () {
    refresh.relaunched();
    if (!doc.hidden) { closeAllMenus(); endReorder(); hideSaver(); setFocus(homeStart()); el.root.scrollTop = 0; }
  });
  root.addEventListener('blur', function () { keys.reset(); });

  // ---- start ----------------------------------------------------------------------------------------------------

  store.followTheme(theme.hash || '');
  resolveConfig();
  applyConfig();
  tickClock();   // schedules the minute tick; applyConfig only draws
  adapter.capabilities(function (err, c) {
    if (err) setProblem('caps', 'Platform check failed: ' + err.message);
    else {
      caps = c;
      if (c.note) setProblem('caps', c.note);
    }
    if (adapter.onAppsChanged) {
      adapter.onAppsChanged(function () { if (refresh.changed()) loadInventory(); });
    }
    loadInventory(function () {
      setFocus(homeStart());
      resetIdle();
      metrics.ready = perf.now();
      root.CYTV.ready = true;   // read by the preview and by acceptance checks; not a network signal
    });
  });
})(window);
