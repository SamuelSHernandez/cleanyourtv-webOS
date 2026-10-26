// The real launcher page and webOS adapter, driven by remote keys under a fake platform.
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { boot, memoryStorage } = require('./harness.js');

const SELF = 'io.github.samuelshernandez.cytvwebos';
const APPS = [
  { id: 'netflix', title: 'Netflix', icon: 'art/0123456789abcdef.png', color: '#141414' },
  { id: 'youtube.leanback.v4', title: 'YouTube', icon: null },
  { id: 'com.plex', title: 'Plex', icon: '../../etc/passwd' },
  { id: 'com.apple.appletv', title: 'Apple TV' },
  { id: 'spotify-beehive', title: 'Spotify' },
  { id: 'com.webos.app.browser', title: 'Web Browser' },
  { id: SELF, title: 'Me', icon: null }
];
const baked = {
  version: 1, synced: '2026-10-26T10:00:00+0000', launcherId: SELF, apps: APPS,
  inputs: [{ app: 'com.webos.app.hdmi1', label: 'HDMI 1' }, { app: 'com.webos.app.hdmi2', label: 'PlayStation' }],
  shortcuts: { inputs: null, settings: 'com.palm.app.settings', livetv: 'com.webos.app.livetv' },
  cards: []
};
const refuseList = (uri) => (uri.endsWith('/listLaunchPoints') ? { returnValue: false, errorText: 'Denied method call' } : { returnValue: true });

function themed(config, extra) {
  return Object.assign({ name: 't', hash: 'a'.repeat(64), config: config, wallpapers: null }, extra || {});
}

async function start(opts) {
  const t = boot(Object.assign({ baked, bridge: refuseList }, opts));
  await t.settle();
  return t;
}

function tileEl(t, key) {
  for (const row of t.doc.getElementById('home').children) {
    for (const c of row.children) if (c.getAttribute('data-key') === key) return c;
  }
  return null;
}

test('Home: the dock is the first row, dock_apps first, filled from the alphabetical rest', async () => {
  const t = await start({});
  assert.deepStrictEqual(t.dock(), ['tile:netflix', 'tile:youtube.leanback.v4', 'tile:com.apple.appletv', 'tile:com.plex']);
  assert.deepStrictEqual(t.tiles().slice(4), ['tile:spotify-beehive', 'tile:com.webos.app.browser']);
  assert.ok(!t.tiles().includes('tile:' + SELF), 'the launcher never lists itself');
  assert.strictEqual(t.focused(), 'tile:netflix');
  assert.deepStrictEqual(t.top(), ['pill:inputs', 'pill:settings']);
  assert.strictEqual(t.doc.getElementById('dock-title').textContent, 'Netflix');
  assert.ok(!tileEl(t, 'tile:com.plex').children.some((c) => c.className === 'art'),
    'an icon path outside the package and the TV is not loaded');
  const m = t.window.CYTV.metrics;
  assert.ok(m.ready >= m.scriptStart && m.builds >= 1 && m.lastBuildMs >= 0, 'timing marks recorded');
});

test('fill_dock false leaves the free dock slots empty, as upstream', async () => {
  const t = await start({ theme: themed({ fill_dock: false }) });
  assert.deepStrictEqual(t.dock(), ['tile:netflix', 'tile:youtube.leanback.v4', null, null]);
  t.key(39); t.key(39);
  assert.strictEqual(t.focused(), 'tile:youtube.leanback.v4', 'focus never lands on an empty slot');
});

test('OK opens the focused app; only listed ids are ever sent', async () => {
  const t = await start({});
  t.key(39);
  t.key(13);
  await t.settle();
  assert.deepStrictEqual(t.launches(), ['youtube.leanback.v4']);
  const res = await new Promise((resolve) => t.window.CYTV.adapter.launch('com.evil.app', resolve));
  assert.match(String(res && res.message), /not an app this launcher listed/);
  const proto = await new Promise((resolve) => t.window.CYTV.adapter.launch('constructor', resolve));
  assert.ok(proto, 'a prototype name is not an allowed id');
  assert.deepStrictEqual(t.launches(), ['youtube.leanback.v4']);
  assert.ok(!t.calls.some((c) => !/\/(launch|listLaunchPoints)$/.test(c.uri)), 'no other service is called');
});

test('Inputs lists Live TV and the TV\'s own inputs; choosing one switches to it', async () => {
  const t = await start({});
  t.key(38);
  assert.strictEqual(t.focused(), 'pill:inputs', 'Up from the first dock tile lands on the first top-bar button');
  t.key(13);
  assert.strictEqual(t.menuTitle(), 'Inputs');
  assert.deepStrictEqual(t.menuLabels(), ['Live TV', 'HDMI 1', 'PlayStation']);
  t.choose('PlayStation');
  await t.settle();
  assert.deepStrictEqual(t.launches(), ['com.webos.app.hdmi2']);
  assert.strictEqual(t.menuOpen(), false);
});

test('Settings opens LG\'s settings; holding OK on it opens the launcher menu', async () => {
  const t = await start({});
  t.key(38);
  t.key(39);
  assert.strictEqual(t.focused(), 'pill:settings');
  t.key(13);
  await t.settle();
  assert.deepStrictEqual(t.launches(), ['com.palm.app.settings']);
  t.hold();
  assert.deepStrictEqual(t.menuLabels(), ['Launcher settings', 'Reorder apps', 'TV system settings']);
  t.key(461);
  assert.strictEqual(t.menuOpen(), false);
});

test('hold OK on a tile: Open, Move and Launcher settings; holding opens nothing', async () => {
  const t = await start({});
  t.hold();
  assert.deepStrictEqual(t.menuLabels(), ['Open', 'Move', 'Launcher settings']);
  assert.deepStrictEqual(t.launches(), []);
});

test('Move: arrows move the app through Home, Back places it, and the order is saved', async () => {
  const t = await start({});
  t.hold();
  t.choose('Move');
  assert.match(t.notice(), /arrows move it/);
  t.key(39); t.key(39);
  assert.deepStrictEqual(t.dock(), ['tile:youtube.leanback.v4', 'tile:com.apple.appletv', 'tile:netflix', 'tile:com.plex']);
  t.key(40);                                    // column 3 has no tile in the row below: it stays
  assert.deepStrictEqual(t.dock()[2], 'tile:netflix');
  t.key(37);
  t.key(40);                                    // column 2 does: out of the dock into the grid
  assert.deepStrictEqual(t.tiles(), ['tile:youtube.leanback.v4', 'tile:com.apple.appletv', 'tile:com.plex',
    'tile:spotify-beehive', 'tile:com.webos.app.browser', 'tile:netflix']);
  assert.strictEqual(t.focused(), 'tile:netflix', 'focus follows the moving app');
  t.key(461);                                   // place
  t.key(461);                                   // finish
  assert.strictEqual(t.notice(), '');
  const stored = JSON.parse(t.storage.data['cytv.prefs']);
  assert.deepStrictEqual(stored.order, ['youtube.leanback.v4', 'com.apple.appletv', 'com.plex', 'spotify-beehive', 'com.webos.app.browser', 'netflix']);
  const again = await start({ storage: t.storage });
  assert.deepStrictEqual(again.tiles(), t.tiles(), 'the saved order wins on the next start');
});

test('Launcher settings: columns, animations and the clock change on the TV; Follow theme undoes them', async () => {
  const t = await start({});
  t.hold();
  t.choose('Launcher settings');
  assert.deepStrictEqual(t.menuLabels(), ['Apps per row', 'Animations: On', 'Clock', 'Follow theme (reset on-TV choices)']);
  assert.deepStrictEqual(t.menuStates().slice(0, 3), ['4', '', 'Off']);
  t.choose('Apps per row');
  assert.strictEqual(t.dock().length, 5, 'five columns: a five-tile dock');
  t.choose('Animations: On');
  assert.match(t.doc.body.className, /anim-off/);
  t.choose('Clock');
  assert.strictEqual(t.menuStates()[2], '5 min');
  assert.deepStrictEqual(JSON.parse(t.storage.data['cytv.prefs']).overrides, { columns: 5, animations: false, home_idle_clock_minutes: 5 });
  t.choose('Follow theme (reset on-TV choices)');
  assert.strictEqual(t.dock().length, 4);
  assert.deepStrictEqual(JSON.parse(t.storage.data['cytv.prefs']).overrides, {});
});

test('a new theme clears the on-TV choices and keeps the order, as a theme push does upstream', async () => {
  const storage = memoryStorage({ 'cytv.prefs': JSON.stringify({ version: 2, order: ['com.plex'], hidden: [], shown: [],
    overrides: { columns: 7 }, theme: 'b'.repeat(64) }) });
  const t = await start({ storage, theme: themed({ columns: 6 }) });
  const p = JSON.parse(storage.data['cytv.prefs']);
  assert.deepStrictEqual(p.overrides, {});
  assert.deepStrictEqual(p.order, ['com.plex']);
  assert.strictEqual(t.dock().length, 6);
  assert.strictEqual(t.dock()[0], 'tile:com.plex');
});

test('theme keys: dock_apps, hidden_apps, app_labels, top_bar_apps, icon_only_buttons, locale', async () => {
  const t = await start({ theme: themed({ dock_apps: ['spotify-beehive'], hidden_apps: ['com.plex'], app_labels: ['netflix=Films'],
    top_bar_apps: ['youtube.leanback.v4'], icon_only_buttons: true, locale: 'fr' }) });
  assert.strictEqual(t.dock()[0], 'tile:spotify-beehive');
  assert.ok(!t.tiles().includes('tile:com.plex'));
  assert.ok(!t.tiles().includes('tile:youtube.leanback.v4'), 'a top-bar app leaves the grid');
  assert.deepStrictEqual(t.top(), ['top:youtube.leanback.v4', 'pill:inputs', 'pill:settings']);
  assert.strictEqual(t.doc.getElementById('topbar').children[1].textContent, 'Sources', 'Inputs in French, from upstream');
  assert.strictEqual(t.doc.getElementById('topbar').children[2].textContent, '', 'Settings as an icon only');
  assert.match(tileEl(t, 'tile:netflix').textContent, /Films/);
});

test('a theme with a bad key keeps every good key and says which one it ignored', async () => {
  const t = await start({ theme: themed({ columns: 99, background_color: 'red', reduced_motion: true, nope: 1 }) });
  assert.strictEqual(t.dock().length, 4);
  assert.match(t.doc.body.className, /anim-reduced/);
  assert.match(t.notice(), /Theme keys ignored: columns, background_color, nope/);
});

test('App library: Remove from Home and Add to Home, choices kept on the TV', async () => {
  const t = await start({ theme: themed({ app_library: true, hidden_apps: ['spotify-beehive'] }) });
  t.hold();
  t.choose('Remove from Home');
  assert.ok(!t.tiles().includes('tile:netflix'));
  const lib = t.doc.getElementById('home').children.find((c) => c.getAttribute('data-key') === 'pill:library');
  assert.ok(lib, 'the App library pill follows the last row');
  t.run('Date.now = function () { return 4e12; }');   // well past the OK click guard
  t.doc.dispatch('click', { target: lib });
  assert.strictEqual(t.menuTitle(), 'App library');
  assert.deepStrictEqual(t.menuLabels(), ['Apple TV', 'Netflix', 'Plex', 'Spotify', 'Web Browser', 'YouTube']);
  assert.deepStrictEqual(t.menuStates(), ['On Home', '', 'On Home', '', 'On Home', 'On Home']);
  t.choose('Spotify');                         // a theme-hidden app, added back by the owner
  t.choose('Netflix');
  assert.ok(t.tiles().includes('tile:spotify-beehive') && t.tiles().includes('tile:netflix'));
  const p = JSON.parse(t.storage.data['cytv.prefs']);
  assert.deepStrictEqual([p.hidden, p.shown], [[], ['spotify-beehive']]);
});

test('module cards: an approved card stands in for its app; an invalid or reserved one is dropped', async () => {
  const cards = [{ spec: 1, app: 'com.plex', label: 'My Movies', caption: 'Plex library', accent: '#E8A33D' },
    { spec: 1, app: 'spotify-beehive', label: 'Official Music' }, { spec: 1, app: 'com.apple.appletv', label: 'Live TV' }];
  const t = await start({ baked: Object.assign({}, baked, { cards }) });
  assert.match(tileEl(t, 'tile:com.plex').textContent, /My Movies · Plex library/);
  assert.doesNotMatch(tileEl(t, 'tile:spotify-beehive').textContent, /Official/);
  assert.doesNotMatch(tileEl(t, 'tile:com.apple.appletv').textContent, /Live TV/);
  const off = await start({ baked: Object.assign({}, baked, { cards }), theme: themed({ module_cards: false }) });
  assert.doesNotMatch(tileEl(off, 'tile:com.plex').textContent, /My Movies/);
});

test('a card feature that fails switches cards off and Home keeps working', async () => {
  const evil = [{ get spec() { throw new Error('boom'); } }];
  const t = await start({ baked: Object.assign({}, baked, { cards: evil }) });
  assert.match(t.notice(), /Module cards switched off: boom/);
  assert.strictEqual(t.dock().length, 4);
});

test('app_keys: a colour button opens its app; reserved keys cannot be mapped', async () => {
  const t = await start({ theme: themed({ app_keys: ['403:netflix', '404:inputs', '13:com.plex'] }) });
  assert.match(t.notice(), /Theme keys ignored: app_keys/, 'one reserved key invalidates the whole list');
  const u = await start({ theme: themed({ app_keys: ['403:netflix', '404:inputs'] }) });
  u.key(403);
  await u.settle();
  assert.deepStrictEqual(u.launches(), ['netflix']);
  u.key(404);
  assert.strictEqual(u.menuTitle(), 'Inputs');
});

test('clock screensaver: shows after the idle time, and the key that wakes Home does nothing else', async () => {
  const t = await start({ theme: themed({ home_idle_clock_minutes: 5 }) });
  t.fire((x) => x.ms === 5 * 60000);
  assert.strictEqual(t.doc.getElementById('screensaver').hidden, false);
  const ev = t.key(13);
  assert.ok(ev.prevented);
  assert.strictEqual(t.doc.getElementById('screensaver').hidden, true);
  await t.settle();
  assert.deepStrictEqual(t.launches(), [], 'waking Home does not open the focused app');
});

test('wallpapers: a collection rotates, captions show, and nothing runs while hidden', async () => {
  const theme = themed({ wallpaper_rotation_minutes: 10, wallpaper_order: 'sequential', wallpaper_captions: true },
    { wallpapers: { single: null, files: ['001.jpg', '002.jpg'], captions: '001.jpg\tDusk\n002.jpg\tDawn' } });
  const t = await start({ theme });
  const img = t.doc.getElementById('wallpaper');
  const first = img.src;
  assert.match(first, /^theme\/wallpapers\/00[12]\.jpg$/);
  t.fire((x) => x.ms === 10 * 60000);
  assert.notStrictEqual(img.src, first);
  assert.match(t.doc.getElementById('caption').textContent, /^(Dusk|Dawn)$/);
  t.doc.hidden = true;
  t.doc.dispatch('visibilitychange', {});
  assert.strictEqual(t.timers.size, 0, 'no timer survives hiding');
});

test('header: greeting with a name, Shamsi and lunar dates when asked', async () => {
  const t = await start({ theme: themed({ greeting_name: 'Sam', shamsi_date: true, lunar_date: true }) });
  assert.match(t.doc.getElementById('greeting').textContent, /^Good (morning|afternoon|evening|night), Sam$/);
  assert.match(t.doc.getElementById('shamsi').textContent, /^\d+ [A-Z][a-z]+ 14\d\d$/);
  assert.match(t.doc.getElementById('lunar').textContent, /^Lunar \d+\//);
});

test('Back on Home does nothing: the launcher never exits itself', async () => {
  const t = await start({});
  const ev = t.key(461);
  assert.ok(ev.prevented);
  assert.deepStrictEqual(t.launches(), []);
});

test('live platform list wins when the platform answers, and a change rebuilds once', async () => {
  let listCalls = 0;
  const first = [{ id: 'live.app', title: 'Live App', largeIcon: '/usr/palm/applications/live.app/icon.png', iconColor: '#112233' }];
  const second = first.concat([{ id: 'new.app', title: 'New App' }]);
  const t = boot({
    baked,
    bridge: (uri) => {
      if (!uri.endsWith('/listLaunchPoints')) return { returnValue: true };
      listCalls++;
      return [{ returnValue: true, launchPoints: listCalls === 1 ? first : second }, { returnValue: true, change: 'added' }];
    }
  });
  await t.settle();
  assert.deepStrictEqual(t.tiles(), ['tile:live.app']);
  assert.strictEqual(t.window.CYTV.adapter.inventorySource(), 'platform');
  const tile = tileEl(t, 'tile:live.app');
  assert.strictEqual(tile.style.background, '#112233');
  assert.strictEqual(tile.children[0].src, 'file:///usr/palm/applications/live.app/icon.png');
  t.calls.filter((c) => c.uri.endsWith('/listLaunchPoints')).pop().bridge.onservicecallback(JSON.stringify({ returnValue: true, change: 'added' }));
  await t.settle();
  assert.strictEqual(listCalls, 2, 'one change, one new request');
  assert.deepStrictEqual(t.tiles(), ['tile:live.app', 'tile:new.app']);
});

test('a silent platform falls back after the call timeout and is asked again later; a refusal is final', async () => {
  let asks = 0;
  const t = boot({ baked, bridge: (uri) => {
    if (!uri.endsWith('/listLaunchPoints')) return { returnValue: true };
    asks++;
    return asks === 1 ? null : { returnValue: true, launchPoints: [{ id: 'live.app', title: 'Live' }] };
  } });
  await t.settle();
  assert.deepStrictEqual(t.tiles(), []);
  t.fire((x) => x.ms === 8000);
  await t.settle();
  assert.strictEqual(t.dock().length, 4);
  t.window.CYTV.adapter.listApps(() => {});
  await t.settle();
  assert.strictEqual(asks, 2);
  assert.strictEqual(t.window.CYTV.adapter.inventorySource(), 'platform');
});

test('not on a TV: the page loads and says so instead of pretending', async () => {
  const t = await start({ baked: null, notWebos: true });
  assert.match(t.notice(), /Not running on a webOS TV/);
  assert.deepStrictEqual(t.tiles(), []);
  assert.match(t.doc.getElementById('home').textContent, /No launchable apps found/);
});

test('corrupt saved preferences are reported and left untouched', async () => {
  const storage = memoryStorage({ 'cytv.prefs': '{broken' });
  const t = await start({ storage, theme: themed({ columns: 5 }) });
  assert.match(t.notice(), /stored preferences are not valid JSON/);
  assert.strictEqual(storage.data['cytv.prefs'], '{broken', 'not overwritten by a theme change');
  assert.strictEqual(t.dock().length, 5);
});

test('milestone-1 preferences are migrated, not dropped', async () => {
  const storage = memoryStorage({ 'cytv.prefs': JSON.stringify({ version: 1, dock: ['com.plex', 'netflix'], hidden: ['spotify-beehive'], seeded: true }) });
  const t = await start({ storage });
  assert.deepStrictEqual(t.dock().slice(0, 2), ['tile:com.plex', 'tile:netflix']);
  assert.ok(!t.tiles().includes('tile:spotify-beehive'));
});

test('clicking a menu item runs that item, not the one the keys left focused', async () => {
  const t = await start({});
  t.hold();
  const settings = t.doc.getElementById('menu-items').children.find((c) => c.textContent === 'Launcher settings');
  t.run('Date.now = function () { return 4e12; }');   // well past the OK click guard
  t.doc.dispatch('click', { target: settings });
  assert.deepStrictEqual(t.launches(), [], 'Open (focused by the keys) must not run');
  assert.strictEqual(t.menuTitle(), 'Launcher settings');
});

test('dock_only: Home shows only dock_apps; everything else waits in the App library', async () => {
  const cfg = { dock_only: true, dock_apps: ['spotify-beehive', 'youtube.leanback.v4', 'com.wbd.stream'], columns: 3 };
  const t = await start({ theme: themed(cfg) });
  assert.deepStrictEqual(t.tiles(), ['tile:spotify-beehive', 'tile:youtube.leanback.v4'], 'an app the TV lacks is skipped');
  const lib = t.doc.getElementById('home').children.find((c) => c.getAttribute('data-key') === 'pill:library');
  assert.ok(lib, 'the App library pill is there without app_library');
  t.key(40);                                    // Down from the dock reaches it
  assert.strictEqual(t.focused(), 'pill:library');
  t.key(13);
  assert.strictEqual(t.menuTitle(), 'App library');
  assert.deepStrictEqual(t.menuStates(), ['', '', '', 'On Home', '', 'On Home']);
  t.choose('Netflix');                          // add one back
  assert.deepStrictEqual(t.tiles(), ['tile:spotify-beehive', 'tile:youtube.leanback.v4', 'tile:netflix']);
  t.key(461);
  const fresh = await start({ theme: themed(cfg), storage: t.storage,
    baked: Object.assign({}, baked, { apps: APPS.concat([{ id: 'new.app', title: 'Brand New' }]) }) });
  assert.ok(!fresh.tiles().includes('tile:new.app'), 'an app installed later stays off Home');
  assert.ok(fresh.tiles().includes('tile:netflix'), 'the app the owner added back stays');
});

test('dock_only off changes nothing (the switch is inert by default)', async () => {
  const a = await start({});
  const b = await start({ theme: themed({ dock_only: false }) });
  assert.deepStrictEqual(a.tiles(), b.tiles());
  assert.ok(!a.doc.getElementById('home').children.some((c) => c.getAttribute('data-key') === 'pill:library'));
});

// ---- regressions from the parity review (2026-10-26) ----------------------------------------------------------

test('the header clock ticks every minute from the start, not only after hiding and showing', async () => {
  const t = await start({});
  const tick = [...t.timers.values()].find((x) => x.ms > 0 && x.ms <= 60050);
  assert.ok(tick, 'a minute tick is scheduled at start');
  t.doc.getElementById('clock').textContent = 'stale';
  t.fire((x) => x === tick);
  assert.match(t.doc.getElementById('clock').textContent, /^\d\d:\d\d$/);
  assert.ok([...t.timers.values()].some((x) => x.ms > 0 && x.ms <= 60050), 'and the next one');
});

test('dock_row false with fill_dock false renders, with no empty slot in the grid', async () => {
  const t = await start({ theme: themed({ dock_row: false, fill_dock: false }) });
  assert.strictEqual(t.window.CYTV.ready, true);
  assert.ok(t.tiles().length > 0 && t.tiles().every((k) => k !== null));
});

test('app ids that are JavaScript property names are just ids', async () => {
  const apps = APPS.concat([{ id: 'constructor', title: 'Constructor App' }, { id: 'toString', title: 'ToString App' }]);
  const t = await start({ baked: Object.assign({}, baked, { apps }), theme: themed({ dock_apps: ['toString', 'valueOf', 'netflix'], app_labels: ['netflix=Films'] }) });
  assert.strictEqual(t.window.CYTV.ready, true);
  assert.deepStrictEqual(t.dock().slice(0, 2), ['tile:toString', 'tile:netflix'], 'valueOf is not an installed app');
  assert.ok(t.tiles().includes('tile:constructor'));
  const res = await new Promise((resolve) => t.window.CYTV.adapter.launch('constructor', resolve));
  assert.strictEqual(res, null, 'an installed app called constructor can be launched');
  const no = await new Promise((resolve) => t.window.CYTV.adapter.launch('hasOwnProperty', resolve));
  assert.ok(no, 'an id that was never listed cannot');
});

test('Move holds the picked app by id, so an inventory change while reordering moves the right app', async () => {
  let launchPoints = APPS.map((a) => ({ id: a.id, title: a.title }));
  const t = boot({ baked, bridge: (uri) => (uri.endsWith('/listLaunchPoints')
    ? [{ returnValue: true, launchPoints }, { returnValue: true, change: 'removed' }] : { returnValue: true }) });
  await t.settle();
  t.key(39); t.key(39);                                  // Apple TV, third in the dock
  t.hold();
  t.choose('Move');
  launchPoints = launchPoints.filter((a) => a.id !== 'netflix');   // an app before it leaves the TV
  t.calls.filter((c) => c.uri.endsWith('/listLaunchPoints')).pop().bridge.onservicecallback(JSON.stringify({ returnValue: true, change: 'removed' }));
  await t.settle();
  t.key(37);
  assert.strictEqual(t.focused(), 'tile:com.apple.appletv');
  assert.strictEqual(t.dock()[0], 'tile:com.apple.appletv', 'Apple TV moved, not the app now at its old index');
});

test('reordering shows no empty dock slots, so moves match what is on screen', async () => {
  const t = await start({ theme: themed({ fill_dock: false }) });
  assert.ok(t.dock().includes(null));
  t.key(38); t.key(39); t.hold();                         // launcher menu from Settings
  t.choose('Reorder apps');
  assert.ok(!t.tiles().includes(null), 'no empty slot while reordering');
  t.key(461);                                            // finish without moving anything
  assert.ok(t.dock().includes(null), 'the empty slots come back: no order was saved');
  assert.strictEqual(JSON.parse(t.storage.data['cytv.prefs'] || '{"order":null}').order, null);
});
