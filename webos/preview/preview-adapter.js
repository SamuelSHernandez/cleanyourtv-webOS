/*
 * PREVIEW ONLY. A simulated platform adapter so the real launcher page can run in a desktop browser. Its apps,
 * inputs and card are invented and nothing it "launches" exists. It lives outside launcher/ and the IPK builder
 * refuses a file with this name, so it cannot reach a TV.
 *
 * Query options: ?apps=0 (empty inventory), ?fail=list (inventory error), ?fail=launch (every launch fails),
 * ?noshortcuts=1, ?storage=off (localStorage throws), ?cards=1 (one approved module card).
 * A theme: start the server with `cytv-webos preview --theme NAME`.
 */
(function (root) {
  'use strict';

  var q = {};
  root.location.search.replace(/^\?/, '').split('&').forEach(function (pair) {
    if (!pair) return;
    var kv = pair.split('=');
    q[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || '');
  });

  // A few ids are the real webOS ids of well-known apps, so dock_apps and first-run order can be seen.
  var names = [['Netflix', 'netflix', '#141414'], ['YouTube', 'youtube.leanback.v4', '#282828'], ['Prime Video', 'amazon', '#1a2a3a'],
    ['Disney+', 'com.disney.disneyplus-prod', '#0d1f4f'], ['Apple TV', 'com.apple.appletv', '#202020'], ['Spotify', 'spotify-beehive', '#121212'],
    ['Plex', 'preview.app.plex', '#1f1f1f'], ['Jellyfin', 'preview.app.jellyfin', '#101a2b'], ['Max', 'com.wbd.stream', '#002be7'],
    ['Pluto TV', 'com.plutotv.app', '#20201a'], ['Web Browser', 'com.webos.app.browser', '#2b3240'], ['Photo & Video', 'preview.app.photos', '#2a2238']];
  var apps = [];
  var count = q.apps !== undefined ? Math.max(0, Math.min(names.length, +q.apps || 0)) : names.length;
  for (var i = 0; i < count; i++) apps.push({ id: names[i][1], title: names[i][0], icon: null, color: names[i][2] });

  var log = [];
  function record(text) {
    log.push(text);
    var out = root.document.getElementById('preview-log');
    if (out) out.textContent = log.slice(-6).join('\n');
  }

  if (q.storage === 'off') {
    try {
      Object.defineProperty(root, 'localStorage', { get: function () { throw new Error('storage disabled for preview'); } });
    } catch (e) { /* some browsers refuse; the preview then keeps working storage */ }
  }

  root.CYTV = root.CYTV || {};
  root.CYTV.baked = { cards: q.cards === '1' ? [{ spec: 1, app: 'preview.app.plex', label: 'Movie Night', caption: 'Plex library', accent: '#E8A33D' }] : [] };

  var changeListener = null;
  root.previewAddApp = function (title) {
    apps.push({ id: 'preview.app.added' + apps.length, title: title, icon: null, color: null });
    if (changeListener) changeListener();
  };

  var shortcuts = q.noshortcuts !== '1';
  root.CYTV.adapter = {
    name: 'preview',
    selfId: 'io.github.samuelshernandez.cytvwebos',
    capabilities: function (cb) {
      cb(null, { backend: 'preview', shortcuts: { inputs: shortcuts, settings: shortcuts, livetv: shortcuts },
        note: 'Preview: simulated apps, nothing is launched.' });
    },
    listApps: function (cb) {
      root.setTimeout(function () {
        if (q.fail === 'list') cb(new Error('simulated inventory failure'));
        else cb(null, apps.slice());
      }, 30);
    },
    inputs: function () {
      return shortcuts ? { inputs: [{ app: 'preview.hdmi1', label: 'HDMI 1' }, { app: 'preview.hdmi2', label: 'PlayStation' }],
        liveTv: 'preview.livetv', picker: null } : { inputs: [], liveTv: null, picker: null };
    },
    onAppsChanged: function (fn) { changeListener = fn; },
    launch: function (id, cb) {
      record('launch ' + id);
      root.setTimeout(function () { cb(q.fail === 'launch' ? new Error('simulated launch failure') : null); }, 30);
    },
    openShortcut: function (kind, cb) {
      record('shortcut ' + kind);
      cb(shortcuts ? null : new Error('not available'));
    },
    inventorySource: function () { return 'preview'; }
  };
})(window);
