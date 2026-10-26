// The calendars ported from the Android launcher, checked against the Android launcher's own test vectors
// (Gathin23/cleanyourtv@f592b6d, launcher/app/src/test/.../LunarTest.java and ShamsiTest.java), plus strings.
'use strict';
const test = require('node:test');
const assert = require('node:assert');
global.CYTV = {};
const clock = require('../../launcher/js/clock.js');
const strings = require('../../launcher/js/strings.js');
const STRINGS = require('../../launcher/js/i18n.js');

const LUNAR = [
  [[10, 2, 2024], 7, [1, 1, 2024, 0]], [[29, 1, 2025], 7, [1, 1, 2025, 0]], [[17, 2, 2026], 7, [1, 1, 2026, 0]],
  [[6, 2, 2027], 7, [1, 1, 2027, 0]], [[16, 2, 2026], 7, [29, 12, 2025, 0]], [[17, 9, 2024], 7, [15, 8, 2024, 0]],
  [[6, 10, 2025], 7, [15, 8, 2025, 0]], [[25, 7, 2025], 7, [1, 6, 2025, 1]], [[25, 6, 2025], 7, [1, 6, 2025, 0]],
  [[22, 1, 2023], 7, [1, 1, 2023, 0]], [[21, 1, 2023], 7, [30, 12, 2022, 0]], [[20, 2, 2023], 7, [1, 2, 2023, 0]],
  [[21, 3, 2023], 7, [30, 2, 2023, 0]], [[22, 3, 2023], 7, [1, 2, 2023, 1]], [[20, 4, 2023], 7, [1, 3, 2023, 0]],
  [[17, 2, 2007], 7, [1, 1, 2007, 0]], [[17, 2, 2007], 8, [30, 12, 2006, 0]], [[18, 2, 2007], 8, [1, 1, 2007, 0]],
  [[21, 1, 1985], 7, [1, 1, 1985, 0]], [[20, 2, 1985], 8, [1, 1, 1985, 0]], [[26, 3, 2009], 8, [30, 2, 2009, 0]],
  [[27, 3, 2009], 8, [1, 3, 2009, 0]], [[23, 4, 2001], 9, [30, 3, 2001, 0]], [[7, 5, 2054], 7, [30, 3, 2054, 0]]
];

test('lunar calendar matches the Android launcher on its own vectors', () => {
  for (const [[d, m, y], tz, want] of LUNAR) {
    assert.deepStrictEqual(clock.fromSolar(d, m, y, tz), want, `${y}-${m}-${d} at UTC+${tz}`);
  }
});

test('every day of 1900-2100 is day 1 to 30 of a lunar month', () => {
  for (const tz of [7, 8]) {
    for (let t = Date.UTC(1900, 0, 1); t < Date.UTC(2101, 0, 1); t += 86400000 * 7) {
      const d = new Date(t);
      const day = clock.fromSolar(d.getUTCDate(), d.getUTCMonth() + 1, d.getUTCFullYear(), tz)[0];
      assert.ok(day >= 1 && day <= 30, `${d.toISOString()} UTC+${tz}: ${day}`);
    }
  }
});

test('Solar Hijri dates match the Android launcher', () => {
  const cases = [[[2021, 3, 21], [1400, 1, 1]], [[2024, 3, 20], [1403, 1, 1]], [[2025, 3, 21], [1404, 1, 1]],
    [[2021, 3, 20], [1399, 12, 30]], [[2022, 3, 20], [1400, 12, 29]], [[2025, 3, 20], [1403, 12, 30]],
    [[1970, 1, 1], [1348, 10, 11]], [[2000, 1, 1], [1378, 10, 11]], [[2026, 9, 22], [1405, 6, 31]]];
  for (const [g, j] of cases) assert.deepStrictEqual(clock.toJalali(g[0], g[1], g[2]), j);
});

test('greetings follow upstream hours, with the Danish late morning', () => {
  assert.strictEqual(clock.greetingKey(4, 'en'), 'good_night');
  assert.strictEqual(clock.greetingKey(11, 'en'), 'good_morning');
  assert.strictEqual(clock.greetingKey(11, 'da'), 'good_forenoon');
  assert.strictEqual(clock.greetingKey(17, 'en'), 'good_evening');
  assert.strictEqual(clock.greetingKey(17, 'da'), 'good_afternoon');
  assert.strictEqual(clock.greetingKey(22, 'en'), 'good_night');
});

test('strings: locale chain, placeholders, arrays and fallbacks', () => {
  const fr = new strings.Strings(STRINGS, 'fr-CA');
  assert.strictEqual(fr.lang, 'fr');
  assert.match(fr.t('cant_open', 'Netflix'), /Netflix/);
  assert.strictEqual(new strings.Strings(STRINGS, 'pt-PT').lang, 'pt');
  assert.strictEqual(new strings.Strings(STRINGS, 'iw').lang, 'he');
  assert.strictEqual(new strings.Strings(STRINGS, 'zh-HK').lang, 'zh-TW');
  assert.strictEqual(new strings.Strings(STRINGS, 'xx').lang, 'en');
  assert.strictEqual(new strings.Strings(STRINGS, '"><script>').lang, 'en');
  const vi = new strings.Strings(STRINGS, 'vi');
  const tet = new Date(2026, 1, 17);
  assert.match(clock.lunar(vi, tet, -1), /^1\/1 âm lịch · Bính Ngọ$/);
  assert.match(clock.lunar(new strings.Strings(STRINGS, 'en'), tet, 8), /Horse/);
  assert.strictEqual(new strings.Strings(STRINGS, 'en').t('no_such_key'), 'no_such_key');
  assert.strictEqual(clock.shamsi(new strings.Strings(STRINGS, 'en'), new Date(2026, 8, 22)), '31 Shahrivar 1405');
});

test('every language has the strings the launcher cannot do without', () => {
  const required = ['inputs', 'settings', 'live_tv', 'cant_open', 'good_morning', 'tile_move', 'library_open'];
  const en = STRINGS.en;
  for (const k of required) assert.ok(en[k], k);
  // How many arguments the launcher passes to each string; a translation may use any of them, and no other.
  const ARGS = { cant_open: 1, greeting_with_name: 2, lunar_year: 2, lunar_date_format: 3, lunar_month_leap: 1,
    animations_state: 1, wallpaper_state: 1, race_countdown_minutes: 1 };
  for (const lang of Object.keys(STRINGS)) {
    for (const [k, v] of Object.entries(STRINGS[lang])) {
      assert.ok(k in en, `${lang}.${k} has no English original`);
      for (const p of (typeof v === 'string' ? v.match(/\{\d\}/g) || [] : [])) {
        assert.ok(+p[1] >= 1 && +p[1] <= (ARGS[k] || 0), `${lang}.${k} uses ${p}, the code passes ${ARGS[k] || 0}`);
      }
      assert.ok(!/<|>/.test(JSON.stringify(v)), `${lang}.${k} has markup`);
    }
  }
});
