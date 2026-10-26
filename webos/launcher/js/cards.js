/*
 * Module cards on webOS (docs/specs/card.md): an add-on app's tile shown as a card, with a label of its
 * choice, an optional caption and an optional glow colour, ahead of the alphabetical grid.
 *
 * The card fields and their rules are the Android launcher's spec 1 (Gathin23/cleanyourtv, docs/specs/card.md).
 * What differs is the trust step: a webOS launcher cannot read another app's files or signing identity, so the
 * owner approves each card on the computer (`cytv-webos addon approve`), and only approved cards are baked into
 * the package. The launcher validates them again here, and shows a card only while its app is installed.
 *
 * Isolation, as upstream's CardFeature: the first failure of any kind switches cards off for the rest of the
 * page's life, and Home goes on exactly as with module_cards false.
 */
(function (root) {
  'use strict';

  var TEXT_RE = /^[A-Za-z0-9.&+' -]+$/;
  var ID_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/;
  // Upstream's reserved names (docs/specs/card.md, "Reserved names"), folded; the launcher adds its own UI names
  // in the TV's language at runtime.
  var RESERVED = ['home', 'settings', 'inputs', 'wifi', 'livetv', 'applibrary', 'choosedefaulthome', 'clock',
    'defaulthome', 'cleanyourtv', 'tvvibehack', 'launchersettings'];
  var MAX_CARDS = 8;

  /** Lower case, everything but ASCII letters and digits removed: "Live TV", "live-tv" and "LIVETV" match. */
  function fold(v) {
    return String(v).toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  function text(v, min, max) {
    return typeof v === 'string' && v.length >= min && v.length <= max && v === v.replace(/^ +| +$/g, '') &&
      TEXT_RE.test(v) && /[A-Za-z0-9]/.test(v) && !/verified|official/.test(fold(v));
  }

  function reservedLabel(label, uiNames) {
    var f = fold(label);
    if (RESERVED.indexOf(f) >= 0 || f.indexOf('hdmi') === 0 || f === 'av') return true;
    for (var i = 0; uiNames && i < uiNames.length; i++) if (fold(uiNames[i]) === f) return true;
    return false;
  }

  /**
   * One card declaration, or null when it breaks a rule (the app then keeps its normal tile). `uiNames`: the
   * launcher's own names in the TV's language, which a card may not take either.
   */
  function validate(c, uiNames) {
    if (!c || typeof c !== 'object' || c.spec !== 1 || typeof c.app !== 'string' || !ID_RE.test(c.app)) return null;
    if (!text(c.label, 1, 24) || reservedLabel(c.label, uiNames)) return null;
    if (c.caption !== undefined && c.caption !== '' && !text(c.caption, 1, 32)) return null;
    if (c.accent !== undefined && !(typeof c.accent === 'string' && /^#[0-9A-Fa-f]{6}$/.test(c.accent))) return null;
    return { app: c.app, label: c.label, caption: c.caption || '', accent: c.accent || null };
  }

  function Feature(report) {
    this.broken = false;
    this.report = report || function () {};
  }

  /** Run one step of the card feature; its fallback once the feature has failed. */
  Feature.prototype.run = function (step, fallback) {
    if (this.broken) return fallback;
    try {
      return step();
    } catch (e) {
      this.broken = true;
      try { this.report(e); } catch (ignored) { /* reporting must not fail Home */ }
      return fallback;
    }
  };

  /**
   * The baked, approved cards as {appId: card}: invalid ones dropped, a label already taken by an earlier card
   * dropped (the list is in decision order, so the oldest decision keeps a name), at most MAX_CARDS.
   */
  function approved(list, uiNames) {
    var out = Object.create(null);
    var labels = [];
    var n = 0;
    if (!Array.isArray(list)) return out;
    for (var i = 0; i < list.length && n < MAX_CARDS; i++) {
      var c = validate(list[i], uiNames);
      if (!c || out[c.app] || labels.indexOf(fold(c.label)) >= 0) continue;
      out[c.app] = c;
      labels.push(fold(c.label));
      n++;
    }
    return out;
  }

  var api = { validate: validate, approved: approved, fold: fold, Feature: Feature, MAX_CARDS: MAX_CARDS, RESERVED: RESERVED };
  root.CYTV = root.CYTV || {};
  root.CYTV.cards = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
