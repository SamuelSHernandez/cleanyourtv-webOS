/*
 * Launcher defaults that are not device-specific. Device-specific choices (LG Home's app id, the
 * shortcut targets) come from the device profile at build time, through inventory.js.
 */
(function (root) {
  'use strict';
  var api = {
    // First-run dock: only those of these that the TV has installed, in this order.
    suggestedDock: ['netflix', 'youtube.leanback.v4', 'amazon', 'com.disney.disneyplus-prod'],
    dockSeedCount: 4
  };
  root.CYTV = root.CYTV || {};
  root.CYTV.profile = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
