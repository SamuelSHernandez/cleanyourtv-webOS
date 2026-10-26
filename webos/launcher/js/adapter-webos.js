/*
 * The platform adapter on a webOS TV (Developer Mode, no root).
 *
 * The page can do exactly these things through it: read capabilities, list apps, list the TV's inputs, launch
 * an id it listed, open a shortcut the build resolved, and be told when the app list changes. There is no
 * generic Luna call, path or URL API: both service URIs below are constants, and every launch id is checked
 * against what this adapter itself listed (apps, inputs, shortcuts) before anything is sent.
 *
 * App list: the platform is asked once per page load (listLaunchPoints). Developer Mode apps may be refused
 * that call; then the list baked in at build time (inventory.js) is used. A refusal is final for the page; a
 * call that got no answer is asked again on the next rebuild.
 */
(function (root) {
  'use strict';

  var C = root.CYTV = root.CYTV || {};
  var CALL_TIMEOUT_MS = 8000;
  var NO_ANSWER = 'no answer from the TV';
  var LAUNCH = 'luna://com.webos.applicationManager/launch';
  var LIST = 'luna://com.webos.applicationManager/listLaunchPoints';
  var ID_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/;
  var COLOR_RE = /^#[0-9A-Fa-f]{6}$/;
  var baked = C.baked || null;
  var bridges = [];       // kept referenced until answered, or the bridge can be collected mid-call
  var allowed = Object.create(null);   // every id a launch may name: listed apps, baked inputs, shortcuts
  var liveList = null;    // null: ask; false: refused; array: the platform's answer
  var liveBridge = null;
  var changeListener = null;

  function hasBridge() {
    return typeof root.PalmServiceBridge !== 'undefined';
  }

  /**
   * One call, one answer: cb(err, payload), bounded by CALL_TIMEOUT_MS. With keepOpen (a subscription), later
   * answers go to keepOpen(payload) until the returned bridge is released.
   */
  function call(uri, payload, cb, keepOpen) {
    if (!hasBridge()) { cb(new Error('not running on a webOS TV')); return null; }
    var done = false;
    var bridge;
    var timer = root.setTimeout(function () { finish(new Error(NO_ANSWER)); }, CALL_TIMEOUT_MS);
    function finish(err, data) {
      if (done) return;
      done = true;
      root.clearTimeout(timer);
      if (!keepOpen || err) release(bridge);
      cb(err, data);
    }
    try {
      bridge = new root.PalmServiceBridge();
      bridges.push(bridge);
      bridge.onservicecallback = function (raw) {
        var data;
        try { data = JSON.parse(raw); } catch (e) { finish(new Error('unreadable answer')); return; }
        if (keepOpen && done) { keepOpen(data); return; }
        if (!data || data.returnValue === false) {
          finish(new Error((data && (data.errorText || data.errorCode)) || 'refused'));
        } else {
          finish(null, data);
        }
      };
      bridge.call(uri, JSON.stringify(payload || {}));
    } catch (e) {
      finish(new Error('service call failed'));
    }
    return bridge;
  }

  function release(bridge) {
    var i = bridges.indexOf(bridge);
    if (i >= 0) bridges.splice(i, 1);
    try { if (bridge && bridge.cancel) bridge.cancel(); } catch (e) { /* already closed */ }
  }

  function localIcon(path) {
    // Only files on the TV: an absolute path from the platform, or the package's own art/ folder.
    if (typeof path !== 'string') return null;
    if (/^art\/[0-9a-f]{16}\.(png|jpg)$/.test(path)) return path;
    if (/^\/[A-Za-z0-9._\/+-]+\.(png|jpg|jpeg)$/i.test(path) && path.indexOf('..') < 0) return 'file://' + path;
    return null;
  }

  function normalize(list, iconKey) {
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < list.length && out.length < 300; i++) {
      var p = list[i];
      if (!p || typeof p.id !== 'string' || !ID_RE.test(p.id) || seen[p.id] || p.hidden === true) continue;
      seen[p.id] = true;
      var title = typeof p.title === 'string' && p.title ? p.title.slice(0, 64) : p.id;
      var color = typeof p.color === 'string' && COLOR_RE.test(p.color) ? p.color
        : typeof p.iconColor === 'string' && COLOR_RE.test(p.iconColor) ? p.iconColor : null;
      out.push({ id: p.id, title: title, icon: localIcon(p[iconKey] || p.icon), color: color });
    }
    return out;
  }

  function bakedApps() {
    return baked && Array.isArray(baked.apps) ? normalize(baked.apps, 'icon') : [];
  }

  function shortcutId(kind) {
    var id = baked && baked.shortcuts ? baked.shortcuts[kind] : null;
    return typeof id === 'string' && ID_RE.test(id) ? id : null;
  }

  function bakedInputs() {
    var out = [];
    var list = baked && Array.isArray(baked.inputs) ? baked.inputs : [];
    for (var i = 0; i < list.length && out.length < 16; i++) {
      var x = list[i];
      if (x && typeof x.app === 'string' && ID_RE.test(x.app) && typeof x.label === 'string' && x.label) {
        out.push({ app: x.app, label: x.label.slice(0, 32) });
      }
    }
    return out;
  }

  function allow(apps) {
    allowed = Object.create(null);
    var i;
    for (i = 0; i < apps.length; i++) allowed[apps[i].id] = true;
    var inputs = bakedInputs();
    for (i = 0; i < inputs.length; i++) allowed[inputs[i].app] = true;
    var kinds = ['inputs', 'settings', 'livetv'];
    for (i = 0; i < kinds.length; i++) if (shortcutId(kinds[i])) allowed[shortcutId(kinds[i])] = true;
    return apps;
  }

  var api = {
    name: 'webos',
    selfId: baked && typeof baked.launcherId === 'string' ? baked.launcherId : null,

    capabilities: function (cb) {
      var note = null;
      if (!hasBridge()) note = 'Not running on a webOS TV: apps cannot be opened from here.';
      else if (!baked || !baked.synced) note = 'This package has no app list: run cytv-webos sync, then build and install again.';
      cb(null, {
        backend: 'webos-devmode',
        shortcuts: { inputs: bakedInputs().length > 0 || !!shortcutId('inputs'), settings: !!shortcutId('settings'), livetv: !!shortcutId('livetv') },
        note: note
      });
    },

    listApps: function (cb) {
      if (liveList === null && hasBridge()) {
        liveBridge = call(LIST, { subscribe: true }, function (err, data) {
          if (err || !data || !Array.isArray(data.launchPoints)) {
            // A refusal is final for this page; silence (a busy TV at boot) is asked again next time.
            liveList = err && err.message === NO_ANSWER ? null : false;
            release(liveBridge);
            liveBridge = null;
            cb(null, allow(bakedApps()));
            return;
          }
          liveList = normalize(data.launchPoints, 'largeIcon');
          cb(null, allow(liveList));
        }, function onChange() {
          // A later answer on the same subscription: the platform's app list changed. Only a subscription that
          // answered in time counts, so a slow platform cannot cause a reload loop.
          if (!Array.isArray(liveList)) return;
          release(liveBridge);
          liveBridge = null;
          liveList = null;
          if (changeListener) changeListener();
        });
        return;
      }
      cb(null, allow(Array.isArray(liveList) ? liveList : bakedApps()));
    },

    /** The TV's inputs (HDMI and the like) from the build, and the Live TV app if the TV has one. */
    inputs: function () {
      return { inputs: bakedInputs(), liveTv: shortcutId('livetv'), picker: shortcutId('inputs') };
    },

    onAppsChanged: function (fn) { changeListener = fn; },

    launch: function (id, cb) {
      if (typeof id !== 'string' || allowed[id] !== true) { cb(new Error('not an app this launcher listed')); return; }
      call(LAUNCH, { id: id }, function (err) { cb(err || null); });
    },

    openShortcut: function (kind, cb) {
      var id = shortcutId(kind);
      if (!id) { cb(new Error('not available on this TV')); return; }
      call(LAUNCH, { id: id }, function (err) { cb(err || null); });
    },

    /** Where the app list came from: 'platform', 'install time (...)' or 'none'. */
    inventorySource: function () {
      return Array.isArray(liveList) ? 'platform' : baked && baked.synced ? 'install time (' + baked.synced + ')' : 'none';
    }
  };

  C.adapter = api;
})(window);
