/*
 * When the launcher rebuilds its tiles. Pure.
 *
 * The idea is upstream's TileRefresh (Gathin23/cleanyourtv, launcher/.../TileRefresh.java): asking
 * for every app again and reloading every icon on each return to Home costs time on a slow TV, so
 * a rebuild happens only when the inventory changed. Change notices that arrive while the launcher
 * is hidden are folded into one rebuild when it comes back.
 */
(function (root) {
  'use strict';

  function Refresh() {
    this.visible = true;
    this.stale = true;      // nothing built yet
    this.refocus = false;
  }

  /** An inventory change notice. True when the launcher should rebuild right now. */
  Refresh.prototype.changed = function () {
    if (this.visible) return true;
    this.stale = true;
    return false;
  };

  /** Another app took the screen. Focus stays where it was, so Back from an app returns to its tile. */
  Refresh.prototype.hidden = function () {
    this.visible = false;
  };

  /** Home was asked for again (relaunch): go back to the first tile. */
  Refresh.prototype.relaunched = function () {
    this.refocus = true;
  };

  /** Back on screen: 'rebuild', 'refocus' or 'nothing'. */
  Refresh.prototype.shown = function () {
    this.visible = true;
    var action = this.stale ? 'rebuild' : this.refocus ? 'refocus' : 'nothing';
    this.stale = false;
    this.refocus = false;
    return action;
  };

  /** A build finished. */
  Refresh.prototype.built = function () {
    this.stale = false;
  };

  /** A build failed: try again on the next return. */
  Refresh.prototype.invalidate = function () {
    this.stale = true;
  };

  var api = { Refresh: Refresh };
  root.CYTV = root.CYTV || {};
  root.CYTV.refresh = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
