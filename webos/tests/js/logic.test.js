// Pure launcher modules: navigation, preferences, model, keys, refresh. Run: node --test webos/tests/js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
global.CYTV = {};
const config = require('../../launcher/js/config.js');
global.CYTV.config = config;
const nav = require('../../launcher/js/nav.js');
const prefs = require('../../launcher/js/prefs.js');
const model = require('../../launcher/js/model.js');
const keys = require('../../launcher/js/keys.js');
const refresh = require('../../launcher/js/refresh.js');

const layout = [
  { id: 'shortcuts', count: 3, columns: 3 },
  { id: 'dock', count: 4, columns: 4 },
  { id: 'grid', count: 10, columns: 8 }
];

test('navigation is deterministic and never wraps', () => {
  let f = nav.first(layout);
  assert.deepStrictEqual(f, { section: 0, index: 0 });
  assert.deepStrictEqual(nav.move(layout, f, 'left'), f);
  assert.deepStrictEqual(nav.move(layout, f, 'up'), f);
  f = nav.move(layout, { section: 0, index: 2 }, 'right');
  assert.deepStrictEqual(f, { section: 0, index: 2 }, 'right edge stays');
  assert.deepStrictEqual(nav.move(layout, { section: 0, index: 2 }, 'down'), { section: 1, index: 2 });
  assert.deepStrictEqual(nav.move(layout, { section: 1, index: 3 }, 'down'), { section: 2, index: 3 });
  assert.deepStrictEqual(nav.move(layout, { section: 1, index: 3 }, 'up'), { section: 0, index: 2 }, 'column clamps to a shorter row');
  assert.deepStrictEqual(nav.move(layout, { section: 2, index: 7 }, 'down'), { section: 2, index: 9 }, 'into a partial last row');
  assert.deepStrictEqual(nav.move(layout, { section: 2, index: 9 }, 'up'), { section: 2, index: 1 });
  assert.deepStrictEqual(nav.move(layout, { section: 2, index: 9 }, 'down'), { section: 2, index: 9 });
  // The same input always gives the same output.
  for (let i = 0; i < 3; i++) assert.deepStrictEqual(nav.move(layout, { section: 2, index: 4 }, 'up'), { section: 1, index: 3 });
});

test('navigation skips empty sections and survives a shrinking layout', () => {
  const sparse = [{ id: 's', count: 0, columns: 1 }, { id: 'd', count: 0, columns: 1 }, { id: 'g', count: 2, columns: 8 }];
  assert.deepStrictEqual(nav.first(sparse), { section: 2, index: 0 });
  assert.deepStrictEqual(nav.move(sparse, { section: 2, index: 1 }, 'up'), { section: 2, index: 1 });
  assert.deepStrictEqual(nav.clamp(sparse, { section: 1, index: 3 }), { section: 2, index: 0 });
  assert.deepStrictEqual(nav.clamp(layout, { section: 2, index: 50 }), { section: 2, index: 9 });
  assert.strictEqual(nav.first([{ id: 'x', count: 0, columns: 1 }]), null);
});

function memoryStorage(initial, failWrites) {
  const data = Object.assign({}, initial);
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { if (failWrites) throw new Error('QuotaExceededError'); data[k] = v; }
  };
}

test('preferences round-trip and validate', () => {
  const s = memoryStorage();
  const store = new prefs.Store(s);
  assert.strictEqual(store.problem, null);
  assert.strictEqual(store.update((p) => { p.order = ['netflix', 'youtube.leanback.v4', 'netflix']; p.overrides.columns = 6; }), true);
  const again = new prefs.Store(s);
  assert.deepStrictEqual(again.prefs.order, ['netflix', 'youtube.leanback.v4'], 'duplicates dropped');
  assert.deepStrictEqual(again.prefs.overrides, { columns: 6 });
  assert.throws(() => again.update((p) => { p.order.push('bad id;'); }));
  assert.throws(() => again.update((p) => { p.overrides.background_color = '#000000'; }), 'only on-TV keys may be overridden');
  assert.throws(() => again.update((p) => { p.overrides.columns = 42; }));
  assert.deepStrictEqual(again.prefs.order, ['netflix', 'youtube.leanback.v4'], 'a refused change changes nothing');
});

test('corrupt or foreign preferences fall back to defaults and say so', () => {
  for (const [text, why] of [['{nope', 'not valid JSON'], ['{"version":3}', 'unsupported version'],
    ['{"version":2,"order":["-rf"],"hidden":[],"shown":[],"overrides":{},"theme":""}', 'failed validation'],
    ['{"version":2,"order":null,"hidden":[],"shown":[],"overrides":{"columns":99},"theme":""}', 'failed validation'],
    ['{"version":1,"dock":"x","hidden":[],"seeded":true}', 'failed validation'], ['[]', 'unsupported version']]) {
    const store = new prefs.Store(memoryStorage({ 'cytv.prefs': text }));
    assert.strictEqual(store.prefs.order, null);
    assert.ok(store.problem && store.problem.includes(why), `${text}: ${store.problem}`);
  }
});

test('version 1 preferences are migrated', () => {
  const store = new prefs.Store(memoryStorage({ 'cytv.prefs': JSON.stringify({ version: 1, dock: ['a.b'], hidden: ['c.d'], seeded: true }) }));
  assert.strictEqual(store.migrated, true);
  assert.deepStrictEqual([store.prefs.order, store.prefs.hidden], [['a.b'], ['c.d']]);
});

test('a new theme clears overrides once; a corrupt store is never overwritten by it', () => {
  const s = memoryStorage();
  const store = new prefs.Store(s);
  store.update((p) => { p.overrides.columns = 5; p.order = ['x.y']; });
  assert.strictEqual(store.followTheme('ab'), true);
  assert.deepStrictEqual([store.prefs.overrides, store.prefs.order, store.prefs.theme], [{}, ['x.y'], 'ab']);
  assert.strictEqual(store.followTheme('ab'), false);
  const bad = memoryStorage({ 'cytv.prefs': '{x' });
  new prefs.Store(bad).followTheme('cd');
  assert.strictEqual(bad.data['cytv.prefs'], '{x');
});

test('storage that refuses writes keeps the launcher working in memory', () => {
  const store = new prefs.Store(memoryStorage({}, true));
  assert.strictEqual(store.update((p) => { p.order = ['netflix']; }), false);
  assert.deepStrictEqual(store.prefs.order, ['netflix']);
  assert.strictEqual(store.persistent, false);
  assert.ok(store.problem);
  const throwing = { getItem() { throw new Error('SecurityError'); } };
  assert.strictEqual(new prefs.Store(throwing).persistent, false);
});

test('model: upstream order, empty dock slots, hidden apps, top-bar apps, cards', () => {
  const apps = [{ id: 'b', title: 'beta' }, { id: 'a', title: 'Alpha' }, { id: 'c', title: 'Gamma' }, { id: 'd', title: 'Delta' },
    { id: 'self', title: 'Me' }];
  const cfg = Object.assign(config.defaults(), { dock_apps: ['c', 'gone'], hidden_apps: ['b'], top_bar_apps: ['d'], columns: 3 });
  const p = prefs.defaults();
  let v = model.build(apps, cfg, p, {}, 'self');
  assert.deepStrictEqual(v.tiles.map((x) => x && x.id), ['c', 'a']);
  assert.deepStrictEqual(v.top.map((x) => x.id), ['d']);
  assert.deepStrictEqual(v.library.map((x) => [x.tile.id, x.onHome]), [['a', true], ['b', false], ['c', true]]);
  v = model.build(apps, Object.assign({}, cfg, { fill_dock: false, hidden_apps: [] }), p, {}, 'self');
  assert.deepStrictEqual(v.tiles.map((x) => x && x.id), ['c', null, null, 'a', 'b'], 'free dock slots stay empty');
  v = model.build(apps, Object.assign({}, cfg, { fill_dock: false, hidden_apps: [] }), Object.assign(p, { order: ['b'] }), {}, 'self');
  assert.deepStrictEqual(v.tiles.map((x) => x && x.id), ['b', 'a', 'c'], 'a saved order wins and has no empty slots');
  v = model.build(apps, Object.assign({}, cfg, { hidden_apps: [] }), prefs.defaults(), { a: { label: 'Zed', caption: '' } }, 'self');
  assert.deepStrictEqual(v.tiles.map((x) => x.title), ['Gamma', 'Zed', 'beta'], 'cards come before the alphabetical rest');
  assert.deepStrictEqual(model.step(5, 3, 0, 'left'), -1);
  assert.deepStrictEqual(model.step(5, 3, 2, 'right'), -1);
  assert.deepStrictEqual(model.step(5, 3, 1, 'down'), 4);
  assert.deepStrictEqual(model.step(5, 3, 2, 'down'), -1);
  assert.deepStrictEqual(model.move(['a', 'b', 'c'], 0, 2), ['b', 'c', 'a']);
});

function fakeTimers() {
  let now = 0;
  let next = 1;
  const pending = new Map();
  return {
    set(fn, ms) { const id = next++; pending.set(id, { at: now + ms, fn }); return id; },
    clear(id) { pending.delete(id); },
    now: () => now,
    advance(ms) {
      now += ms;
      for (const [id, t] of [...pending]) if (t.at <= now) { pending.delete(id); t.fn(); }
    }
  };
}

function recorder() {
  const log = [];
  return { log, move: (d) => log.push('move:' + d), activate: () => log.push('activate'), hold: () => log.push('hold'), back: () => log.push('back') };
}

test('OK activates on release; holding opens the menu instead, never both', () => {
  const t = fakeTimers();
  const r = recorder();
  const k = new keys.Keys(r, t);
  k.keydown(13, false); t.advance(100); k.keyup(13);
  assert.deepStrictEqual(r.log, ['activate']);
  k.keydown(13, false); t.advance(keys.HOLD_MS + 10);
  k.keydown(13, false); k.keydown(13, true);      // webOS repeats, with and without e.repeat
  k.keyup(13);
  assert.deepStrictEqual(r.log, ['activate', 'hold']);
});

test('arrow repeats keep moving; other keys keep their system meaning', () => {
  const t = fakeTimers();
  const r = recorder();
  const k = new keys.Keys(r, t);
  assert.ok(k.keydown(39, false)); assert.ok(k.keydown(39, true)); assert.ok(k.keydown(39, true));
  assert.deepStrictEqual(r.log, ['move:right', 'move:right', 'move:right']);
  for (const code of [447, 448, 449, 33, 34, 36, 1001, 457, 1056]) {   // volume, mute, channel, home, settings, inputs
    assert.strictEqual(k.keydown(code, false), false, 'key ' + code + ' must not be swallowed');
  }
  assert.ok(k.keydown(461, false));
  assert.deepStrictEqual(r.log.slice(-1), ['back']);
});

test('a click right after an OK activation is the same press, not a second launch', () => {
  const t = fakeTimers();
  const k = new keys.Keys(recorder(), t);
  k.keydown(13, false); k.keyup(13);
  t.advance(50);
  assert.strictEqual(k.click(), false);
  t.advance(keys.CLICK_GUARD_MS);
  assert.strictEqual(k.click(), true);
});

test('a press interrupted by hiding the page fires nothing later', () => {
  const t = fakeTimers();
  const r = recorder();
  const k = new keys.Keys(r, t);
  k.keydown(13, false);
  k.reset();
  t.advance(keys.HOLD_MS * 2);
  k.keyup(13);
  assert.deepStrictEqual(r.log, []);
});

test('refresh: rebuild only when the inventory changed, once for many changes', () => {
  const f = new refresh.Refresh();
  f.built();
  f.hidden();
  assert.strictEqual(f.changed(), false);
  assert.strictEqual(f.changed(), false);
  assert.strictEqual(f.shown(), 'rebuild');
  f.hidden();
  assert.strictEqual(f.shown(), 'nothing', 'Back from an app keeps the focus where it was');
  f.hidden();
  f.relaunched();
  assert.strictEqual(f.shown(), 'refocus');
  assert.strictEqual(f.changed(), true, 'visible: rebuild now');
});
