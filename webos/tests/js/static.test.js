// Source checks that guard properties no runtime test can see: ES5 syntax for old webOS engines,
// the content security policy, no network or eval in the launcher, and preview/TV markup in step.
// The ES5 check is a token scan (strings, comments and regex bodies removed first), not a parser:
// it catches the ES2015+ syntax this code could plausibly grow, not every possible construct.
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '../..');
const JS = path.join(ROOT, 'launcher/js');
const launcherFiles = fs.readdirSync(JS).filter((f) => f.endsWith('.js')).map((f) => path.join(JS, f));

function stripLiterals(src) {
  let out = '';
  let i = 0;
  let prev = '';
  while (i < src.length) {
    const c = src[i];
    const d = src[i + 1];
    if (c === '/' && d === '/') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (c === '/' && d === '*') { i = src.indexOf('*/', i + 2) + 2; continue; }
    if (c === '"' || c === "'") {
      i++;
      while (i < src.length && src[i] !== c) i += src[i] === '\\' ? 2 : 1;
      i++; out += '""'; prev = '"'; continue;
    }
    if (c === '`') { out += '`'; i++; continue; }        // reported below as ES2015
    if (c === '/' && /[(,=:[!&|?{};]/.test(prev)) {      // a regex literal
      i++;
      let inClass = false;
      while (i < src.length && (src[i] !== '/' || inClass)) {
        if (src[i] === '\\') i++;
        else if (src[i] === '[') inClass = true;
        else if (src[i] === ']') inClass = false;
        i++;
      }
      i++;
      while (/[a-z]/.test(src[i] || '')) i++;
      out += '/r/'; prev = 'r'; continue;
    }
    out += c;
    if (!/\s/.test(c)) prev = c;
    i++;
  }
  return out;
}

const ES2015 = [
  [/\b(let|const|class)\s/, 'let/const/class'],
  [/=>/, 'arrow function'],
  [/`/, 'template literal'],
  [/\.\.\./, 'spread/rest'],
  [/\bfor\s*\([^)]*\bof\b/, 'for...of'],
  [/\b(async|await|yield)\b/, 'async/generators'],
  [/\bfunction\s*\*/, 'generator'],
  [/\?\?|\?\./, 'nullish/optional chaining'],
  [/\b(Promise|Symbol|Map|Set|WeakMap|Proxy|Reflect)\b/, 'ES2015 global'],
  [/\.(includes|startsWith|endsWith|find|findIndex|padStart|assign)\(/, 'ES2015+ method']
];

test('launcher scripts use ES5 syntax only (webOS 3.x engines)', () => {
  for (const file of launcherFiles) {
    const code = stripLiterals(fs.readFileSync(file, 'utf8'))
      .replace(/typeof module !== ""[^\n]*/g, '')          // the Node export line
      .replace(/typeof window !== "" \? window : globalThis/g, '');
    for (const [re, what] of ES2015) {
      assert.ok(!re.test(code), `${path.basename(file)} uses ${what}: ${(code.match(re) || [])[0]}`);
    }
  }
});

test('the token scan itself catches ES2015 syntax', () => {
  for (const sample of ['let x = 1;', 'var f = (a) => a;', 'var s = `x`;', 'f(...a);', 'for (var x of y) {}']) {
    const code = stripLiterals(sample);
    assert.ok(ES2015.some(([re]) => re.test(code)), sample);
  }
  assert.ok(!ES2015.some(([re]) => re.test(stripLiterals('var s = "let x => `y`"; var r = /a=>b/g;'))));
});

test('no network, eval or HTML injection in the launcher', () => {
  for (const file of launcherFiles) {
    const code = stripLiterals(fs.readFileSync(file, 'utf8'));
    for (const re of [/\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/, /\beval\s*\(/, /new\s+Function/, /\.innerHTML\b/,
      /\.outerHTML\b/, /insertAdjacentHTML/, /document\.write/, /importScripts/, /\bsendBeacon\b/]) {
      assert.ok(!re.test(code), `${path.basename(file)} matches ${re}`);
    }
  }
});

test('the only service URIs the TV adapter can call are fixed constants', () => {
  const src = fs.readFileSync(path.join(JS, 'adapter-webos.js'), 'utf8');
  const uris = src.match(/luna:\/\/[A-Za-z0-9./]+/g);
  assert.deepStrictEqual([...new Set(uris)].sort(), ['luna://com.webos.applicationManager/launch',
    'luna://com.webos.applicationManager/listLaunchPoints']);
  for (const f of launcherFiles) {
    if (!f.endsWith('adapter-webos.js')) assert.ok(!/luna:\/\/|PalmServiceBridge/.test(fs.readFileSync(f, 'utf8')), `${path.basename(f)} talks to the platform directly`);
  }
  assert.ok(!/call\(\s*[a-z]+\s*\+/.test(src), 'no URI is built from data');
});

test('index.html: strict CSP, no inline script or handlers, nothing remote', () => {
  const html = fs.readFileSync(path.join(ROOT, 'launcher/index.html'), 'utf8');
  const csp = (html.match(/Content-Security-Policy" content="([^"]+)"/) || [])[1];
  assert.ok(csp, 'CSP meta present');
  assert.match(csp, /default-src 'none'/);
  // webOS loads the app from file://, an opaque origin 'self' does not match (observed on webOS 22, Chrome 87:
  // every script was refused and the screen stayed black), so the package's own files are allowed as file:.
  assert.match(csp, /script-src 'self' file:(;|$)/);
  assert.match(csp, /style-src 'self' file:(;|$)/);
  assert.match(csp, /connect-src 'none'/);
  assert.ok(!/unsafe-inline|unsafe-eval|https?:/.test(csp));
  assert.ok(!/<script>[^<]/.test(html) && !/<script(?![^>]*\ssrc=)/.test(html), 'every script is an external file');
  assert.ok(!/\son[a-z]+=/.test(html), 'no inline event handlers');
  for (const file of launcherFiles.concat([path.join(ROOT, 'launcher/index.html'), path.join(ROOT, 'launcher/css/launcher.css')])) {
    const text = fs.readFileSync(file, 'utf8');
    assert.ok(!/https?:\/\/(?!www\.w3\.org)/.test(text), `${path.basename(file)} references a remote URL`);
  }
});

test('the preview runs the same markup and scripts as the TV page', () => {
  const tv = fs.readFileSync(path.join(ROOT, 'launcher/index.html'), 'utf8');
  const pv = fs.readFileSync(path.join(ROOT, 'preview/index.html'), 'utf8');
  const body = (h) => h.slice(h.indexOf('<div id="backdrop"'), h.indexOf('<div id="screensaver"')).replace(/\s+/g, ' ');
  assert.strictEqual(body(pv), body(tv));
  const scripts = (h) => (h.match(/src="[^"]+"/g) || []).map((s) => s.replace(/^src="(\.\.\/launcher\/)?/, '').replace(/"$/, ''));
  const tvScripts = scripts(tv).filter((s) => !['js/adapter-webos.js', 'js/inventory.js', 'js/theme.js'].includes(s));
  const pvScripts = scripts(pv).filter((s) => !['preview-adapter.js', 'theme.js'].includes(s));
  assert.deepStrictEqual(pvScripts, tvScripts);
});

test('launcher CSS stays inside Chromium 38 (webOS 3.x)', () => {
  const css = fs.readFileSync(path.join(ROOT, 'launcher/css/launcher.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const [re, what] of [[/var\(--|--[a-z-]+\s*:/, 'custom properties (Chrome 49)'], [/display:\s*(inline-)?grid/, 'grid (Chrome 57)'],
    [/(^|[\s;{])gap\s*:/, 'flex/grid gap (Chrome 84)'], [/backdrop-filter/, 'backdrop-filter'], [/:is\(|:where\(|:has\(/, 'modern selectors'],
    [/aspect-ratio/, 'aspect-ratio (Chrome 88)'], [/\binset\s*:/, 'inset shorthand (Chrome 87)'], [/@import|url\(\s*['"]?https?:/, 'remote or imported CSS']]) {
    assert.ok(!re.test(css), `launcher.css uses ${what}`);
  }
});

test('generated i18n.js names its upstream source commit and licence', () => {
  const head = fs.readFileSync(path.join(ROOT, 'launcher/js/i18n.js'), 'utf8').slice(0, 600);
  assert.match(head, /Gathin23\/cleanyourtv@[0-9a-f]{40}/);
  assert.match(head, /MIT/);
});
