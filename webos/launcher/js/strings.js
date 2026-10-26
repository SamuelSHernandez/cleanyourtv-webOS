/*
 * Text in the launcher's language. The table is CYTV.STRINGS (i18n.js, imported from the Android launcher's
 * resources); the language is the theme's `locale` when set, else the TV's. A string a language lacks falls
 * back along the same chain Android uses: pt-PT -> pt -> en.
 */
(function (root) {
  'use strict';

  var ALIASES = { iw: 'he', 'in': 'id', no: 'nb', 'sr-latn': 'sr-Latn', 'zh-hans': 'zh-CN', 'zh-hant': 'zh-TW' };

  function canonical(tag) {
    if (typeof tag !== 'string' || !/^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})*$/.test(tag)) return null;
    var parts = tag.replace(/_/g, '-').split('-');
    var lang = parts[0].toLowerCase();
    var out = [lang];
    for (var i = 1; i < parts.length; i++) {
      var p = parts[i];
      out.push(p.length === 2 ? p.toUpperCase() : p.length === 4 ? p.charAt(0).toUpperCase() + p.slice(1).toLowerCase() : p);
    }
    return out.join('-');
  }

  /** The tables to look in, most specific first, always ending in English. */
  function chain(tag, table) {
    var out = [];
    function add(t) { if (t && table[t] && out.indexOf(t) < 0) out.push(t); }
    var c = canonical(tag);
    if (c) {
      add(ALIASES[c.toLowerCase()] || c);
      var parts = c.split('-');
      // zh-HK and zh-Hant read Traditional; other zh variants Simplified.
      if (parts[0] === 'zh') add(/^(TW|HK|MO|Hant)$/.test(parts[1] || '') ? 'zh-TW' : 'zh-CN');
      if (parts.length > 2) add(parts[0] + '-' + parts[1]);
      add(ALIASES[parts[0]] || parts[0]);
    }
    add('en');
    return out;
  }

  function Strings(table, tag) {
    this.table = table || { en: {} };
    this.order = chain(tag, this.table);
    this.lang = this.order[0];
  }

  /** t('cant_open', 'Netflix'): the string with {1}, {2}... filled in; the key itself if no table has it. */
  Strings.prototype.t = function (key) {
    var text = null;
    for (var i = 0; i < this.order.length && text === null; i++) {
      var s = this.table[this.order[i]][key];
      if (typeof s === 'string') text = s;
    }
    if (text === null) return key;
    var args = arguments;
    return text.replace(/\{(\d)\}/g, function (m, n) {
      var v = args[+n];
      return v === undefined ? m : String(v);
    });
  };

  /** A string array (lunar stems and branches): the first table in the chain that has it. */
  Strings.prototype.list = function (key) {
    for (var i = 0; i < this.order.length; i++) {
      var v = this.table[this.order[i]][key];
      if (Array.isArray(v)) return v;
    }
    return [];
  };

  var api = { Strings: Strings, chain: chain, canonical: canonical };
  root.CYTV = root.CYTV || {};
  root.CYTV.strings = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
