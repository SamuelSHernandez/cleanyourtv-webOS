/*
 * What the owner chose on the TV: Home's order (once they moved an app), apps taken off or added back through
 * the App library, and the Launcher settings choices. One localStorage key, validated on every read; nothing
 * leaves the TV.
 *
 * As upstream: a new theme clears the Launcher settings choices (columns, motion, clock, wallpaper), and keeps
 * the order and the App library choices. Version 1 (milestone 1: a dock list and hidden apps) is migrated, never
 * dropped. A stored value that does not parse or validate is not "repaired": the launcher starts from defaults,
 * leaves the bad value untouched until the owner changes something, and reports it.
 */
(function (root) {
  'use strict';

  var KEY = 'cytv.prefs';
  var VERSION = 2;
  var MAX_IDS = 300;
  var ID_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/;
  var THEME_RE = /^[0-9a-f]{0,64}$/;

  function defaults() {
    return { version: VERSION, order: null, hidden: [], shown: [], overrides: {}, theme: '' };
  }

  function cleanIds(value) {
    if (!Array.isArray(value)) return null;
    var out = [];
    for (var i = 0; i < value.length; i++) {
      var id = value[i];
      if (typeof id !== 'string' || !ID_RE.test(id)) return null;
      if (out.indexOf(id) < 0) out.push(id);
    }
    return out.length > MAX_IDS ? null : out;
  }

  function cleanOverrides(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    var schema = root.CYTV.config.SCHEMA;
    var out = {};
    for (var k in value) {
      if (!Object.prototype.hasOwnProperty.call(value, k)) continue;
      if (!schema.hasOwnProperty(k) || !schema[k].onTv || !root.CYTV.config.check(schema[k], value[k])) return null;
      out[k] = value[k];
    }
    return out;
  }

  function fromV1(data) {
    var dock = cleanIds(data.dock);
    var hidden = cleanIds(data.hidden);
    if (!dock || !hidden || typeof data.seeded !== 'boolean') return null;
    var p = defaults();
    p.order = dock.length ? dock : null;
    p.hidden = hidden;
    return p;
  }

  /** { prefs, problem, migrated }: problem is null, or why the stored value was not used. */
  function parse(text) {
    if (text === null || text === undefined) return { prefs: defaults(), problem: null, migrated: false };
    var data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      return { prefs: defaults(), problem: 'stored preferences are not valid JSON', migrated: false };
    }
    if (data && data.version === 1) {
      var old = fromV1(data);
      return old ? { prefs: old, problem: null, migrated: true }
        : { prefs: defaults(), problem: 'stored preferences failed validation', migrated: false };
    }
    if (!data || typeof data !== 'object' || data.version !== VERSION) {
      return { prefs: defaults(), problem: 'stored preferences have an unsupported version', migrated: false };
    }
    var order = data.order === null ? null : cleanIds(data.order);
    var hidden = cleanIds(data.hidden);
    var shown = cleanIds(data.shown);
    var overrides = cleanOverrides(data.overrides);
    if ((data.order !== null && !order) || !hidden || !shown || !overrides || typeof data.theme !== 'string' || !THEME_RE.test(data.theme)) {
      return { prefs: defaults(), problem: 'stored preferences failed validation', migrated: false };
    }
    return { prefs: { version: VERSION, order: order, hidden: hidden, shown: shown, overrides: overrides, theme: data.theme },
      problem: null, migrated: false };
  }

  function serialize(p) {
    var order = p.order === null ? null : cleanIds(p.order);
    var hidden = cleanIds(p.hidden);
    var shown = cleanIds(p.shown);
    var overrides = cleanOverrides(p.overrides);
    if ((p.order !== null && !order) || !hidden || !shown || !overrides || typeof p.theme !== 'string' || !THEME_RE.test(p.theme)) {
      throw new Error('refusing to store invalid preferences');
    }
    return JSON.stringify({ version: VERSION, order: order, hidden: hidden, shown: shown, overrides: overrides, theme: p.theme });
  }

  function clone(p) {
    return { version: VERSION, order: p.order ? p.order.slice() : null, hidden: p.hidden.slice(), shown: p.shown.slice(),
      overrides: JSON.parse(JSON.stringify(p.overrides)), theme: p.theme };
  }

  /**
   * A store over a Storage-like object ({getItem, setItem}). Storage that throws leaves the launcher working
   * from memory, with `persistent` false so the UI can say changes will not survive a restart.
   */
  function Store(storage) {
    this.storage = storage;
    this.persistent = !!storage;
    this.problem = null;
    var text = null;
    try {
      text = storage ? storage.getItem(KEY) : null;
    } catch (e) {
      this.persistent = false;
      this.problem = 'preferences cannot be read on this TV';
    }
    var parsed = parse(text);
    this.prefs = parsed.prefs;
    this.migrated = parsed.migrated;
    if (parsed.problem) this.problem = parsed.problem;
  }

  /** Apply a change and write it. True when stored, false when only kept in memory. Throws if invalid. */
  Store.prototype.update = function (change) {
    var next = clone(this.prefs);
    change(next);
    var text = serialize(next);
    this.prefs = next;
    if (!this.persistent) return false;
    try {
      this.storage.setItem(KEY, text);
      this.problem = null;
      return true;
    } catch (e) {
      this.persistent = false;
      this.problem = 'preferences could not be saved (storage refused the write)';
      return false;
    }
  };

  /** A different theme than last time: its own settings win again, as after a theme push upstream. */
  Store.prototype.followTheme = function (themeHash) {
    if (this.prefs.theme === themeHash || this.problem) return false;
    return this.update(function (p) { p.overrides = {}; p.theme = themeHash; });
  };

  var api = { KEY: KEY, VERSION: VERSION, MAX_IDS: MAX_IDS, parse: parse, serialize: serialize, Store: Store, defaults: defaults };
  root.CYTV = root.CYTV || {};
  root.CYTV.prefs = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
