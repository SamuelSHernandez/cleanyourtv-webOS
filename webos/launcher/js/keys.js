/*
 * Remote keys to launcher actions. Pure apart from the injected timer functions.
 * webOS repeating OK without e.repeat: observed in lasharor/cleanyourtv-WebOS@5667cd5 (app/src/js/input.js).
 *
 * - Arrows move focus on keydown, repeats included (holding a direction keeps moving).
 * - OK activates on keyup. Held for HOLD_MS it opens the tile menu instead, and the keyup that
 *   follows is swallowed. OK repeats are ignored, so a held OK never launches twice.
 * - Back closes what is open; on the home screen it does nothing, so the launcher never exits
 *   itself.
 * - A click within CLICK_GUARD_MS of an OK activation is ignored: on webOS a Magic Remote OK
 *   press can arrive as a key and as a click.
 * - Every other key is not handled here and keeps its system meaning (volume, mute, channel,
 *   Inputs, Settings, Home).
 */
(function (root) {
  'use strict';

  var KEY = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, OK: 13, BACK: 461, ESC: 27 };
  var HOLD_MS = 600;
  var CLICK_GUARD_MS = 400;

  function Keys(handlers, timers) {
    this.h = handlers;           // { move(dir), activate(), hold(), back() }
    this.t = timers;             // { set(fn, ms) -> token, clear(token), now() -> ms }
    this.okDown = false;
    this.okTimer = null;
    this.held = false;
    this.lastActivate = -Infinity;
  }

  /** Returns true when the event was handled (the caller then prevents its default). */
  Keys.prototype.keydown = function (code, repeat) {
    var self = this;
    switch (code) {
      case KEY.LEFT: this.h.move('left'); return true;
      case KEY.RIGHT: this.h.move('right'); return true;
      case KEY.UP: this.h.move('up'); return true;
      case KEY.DOWN: this.h.move('down'); return true;
      case KEY.OK:
        if (repeat || this.okDown) return true;
        this.okDown = true;
        this.held = false;
        this.okTimer = this.t.set(function () {
          self.okTimer = null;
          self.held = true;
          self.h.hold();
        }, HOLD_MS);
        return true;
      case KEY.BACK:
      case KEY.ESC:
        this.h.back();
        return true;
      default:
        return false;
    }
  };

  Keys.prototype.keyup = function (code) {
    if (code !== KEY.OK) return false;
    if (!this.okDown) return true;   // the keydown went elsewhere (another app, a dialog)
    this.okDown = false;
    if (this.okTimer !== null) {
      this.t.clear(this.okTimer);
      this.okTimer = null;
    }
    if (!this.held) {
      this.lastActivate = this.t.now();
      this.h.activate();
    }
    this.held = false;
    return true;
  };

  /** A pointer click on a tile. False when it duplicates an OK key activation. */
  Keys.prototype.click = function () {
    return this.t.now() - this.lastActivate >= CLICK_GUARD_MS;
  };

  /** The page lost focus or was hidden mid-press: forget the press so nothing fires later. */
  Keys.prototype.reset = function () {
    if (this.okTimer !== null) this.t.clear(this.okTimer);
    this.okTimer = null;
    this.okDown = false;
    this.held = false;
  };

  var api = { KEY: KEY, HOLD_MS: HOLD_MS, CLICK_GUARD_MS: CLICK_GUARD_MS, Keys: Keys };
  root.CYTV = root.CYTV || {};
  root.CYTV.keys = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
