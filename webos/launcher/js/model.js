/*
 * What Home shows, from the app inventory, the effective config and the local preferences. Pure.
 *
 * The model is the Android launcher's: Home is one ordered list of tiles and the dock is its first row
 * (`columns` tiles). Without a saved order, `dock_apps` (the ones installed) come first, then add-on cards,
 * then every other app by name. Once the owner moves an app on the TV, that saved order wins; apps installed
 * later join the end. With `fill_dock` false and no saved order, dock slots `dock_apps` leaves free stay empty.
 */
(function (root) {
  'use strict';

  function byTitle(a, b) {
    var x = a.title.toLowerCase();
    var y = b.title.toLowerCase();
    return x < y ? -1 : x > y ? 1 : (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  }

  function has(list, id) {
    return list.indexOf(id) >= 0;
  }

  /**
   * apps: [{id, title, icon, color}], cfg: effective config, prefs: {order, hidden, shown},
   * cards: {appId: {label, caption, accent}} already validated and approved, selfId: this launcher.
   */
  function build(apps, cfg, prefs, cards, selfId, opts) {
    opts = opts || {};
    // Maps keyed by app id have no prototype: an id like "constructor" or "toString" is just an id.
    cards = cfg.module_cards && cards ? cards : Object.create(null);
    var labels = root.CYTV.config.labels(cfg.app_labels);
    var top = [];
    var library = [];
    var onHome = [];
    for (var i = 0; i < apps.length; i++) {
      var a = apps[i];
      if (a.id === selfId) continue;
      var tile = { id: a.id, title: labels[a.id] || a.title, icon: a.icon || null, color: a.color || null, card: null };
      if (cards[a.id]) {
        tile.card = cards[a.id];
        tile.title = cards[a.id].label;
      }
      if (has(cfg.top_bar_apps, a.id)) { top.push(tile); continue; }
      // dock_only: an app is on Home only when the config or the owner put it there (or it carries a card).
      var offHome = has(cfg.hidden_apps, a.id) || (cfg.dock_only && !has(cfg.dock_apps, a.id) && !tile.card);
      var hidden = (offHome && !has(prefs.shown, a.id)) || has(prefs.hidden, a.id);
      library.push({ tile: tile, onHome: !hidden });
      if (!hidden) onHome.push(tile);
    }
    library.sort(function (x, y) { return byTitle(x.tile, y.tile); });
    var orderTop = [];
    for (var t = 0; t < cfg.top_bar_apps.length; t++) {
      for (var u = 0; u < top.length; u++) if (top[u].id === cfg.top_bar_apps[t]) orderTop.push(top[u]);
    }

    var byId = Object.create(null);
    for (var j = 0; j < onHome.length; j++) byId[onHome[j].id] = onHome[j];
    var head = [];
    var saved = Array.isArray(prefs.order);
    var lead = saved ? prefs.order : cfg.dock_apps;
    for (var k = 0; k < lead.length; k++) {
      if (byId[lead[k]] && !has(head, byId[lead[k]])) head.push(byId[lead[k]]);
    }
    var docked = head.length;
    var rest = [];
    for (var r = 0; r < onHome.length; r++) if (!has(head, onHome[r])) rest.push(onHome[r]);
    var withCards = rest.filter(function (x) { return x.card; }).sort(byTitle);
    var plain = rest.filter(function (x) { return !x.card; }).sort(byTitle);
    var tiles = head.concat(withCards, plain);

    var columns = cfg.columns;
    var empty = 0;
    // As upstream (DockSlots): empty slots only in a dock row, and never while reordering.
    if (!saved && !cfg.fill_dock && !cfg.dock_only && cfg.dock_row && !opts.reordering &&
        docked > 0 && docked < columns && tiles.length > docked) empty = columns - docked;
    var slots = tiles.slice(0, docked);
    for (var e = 0; e < empty; e++) slots.push(null);
    slots = slots.concat(tiles.slice(docked));
    return { tiles: slots, dockSize: Math.min(columns, slots.length), top: orderTop, library: library };
  }

  /** The ids in Home's order (empty slots dropped): what a reorder saves. */
  function orderOf(tiles) {
    var out = [];
    for (var i = 0; i < tiles.length; i++) if (tiles[i]) out.push(tiles[i].id);
    return out;
  }

  /** Move the tile at `from` by one step on a grid of `columns`; returns the new index, or -1 if it cannot. */
  function step(count, columns, from, direction) {
    var to = from;
    if (direction === 'left') to = from % columns === 0 ? -1 : from - 1;
    else if (direction === 'right') to = (from + 1) % columns === 0 || from + 1 >= count ? -1 : from + 1;
    else if (direction === 'up') to = from - columns;
    else if (direction === 'down') to = from + columns >= count ? -1 : from + columns;
    return to >= 0 && to < count ? to : -1;
  }

  function move(ids, from, to) {
    var out = ids.slice();
    var id = out.splice(from, 1)[0];
    out.splice(to, 0, id);
    return out;
  }

  var api = { build: build, orderOf: orderOf, step: step, move: move, byTitle: byTitle };
  root.CYTV = root.CYTV || {};
  root.CYTV.model = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
