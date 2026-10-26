// A minimal DOM and webOS stand-in for running the real launcher scripts under Node's vm.
// It implements only what launcher/js/*.js touches; it is not a browser and proves nothing about a TV's
// engine (docs/hardware-acceptance.md is where that is shown).
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const LAUNCHER = path.resolve(__dirname, '../../launcher');
const SCRIPTS = (() => {
  const html = fs.readFileSync(path.join(LAUNCHER, 'index.html'), 'utf8');
  return (html.match(/src="js\/[^"]+"/g) || []).map((s) => s.slice(5, -1));
})();

class Node {
  constructor(tag, doc) {
    this.tagName = (tag || '').toUpperCase();
    this.ownerDocument = doc;
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.className = '';
    this.hidden = false;
    this._text = '';
    this.style = {};
    this.offsetTop = 0;
    this.offsetHeight = 100;
    this.clientHeight = 1080;
    this.scrollTop = 0;
    this.listeners = {};
  }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { c.parentNode = this; this.children.push(c); c.offsetTop = this.children.length * 120; return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
}

const IDS = ['backdrop', 'sky', 'wallpaper', 'wallpaper-dim', 'root', 'when', 'greeting', 'clock', 'date', 'shamsi',
  'lunar', 'topbar', 'caption', 'spacer', 'dock-title', 'home', 'notice', 'menu', 'menu-title', 'menu-hint',
  'menu-items', 'screensaver', 'ss-wallpaper', 'ss-dim', 'ss-glow', 'ss-time'];
const HIDDEN = ['menu', 'notice', 'screensaver', 'caption', 'shamsi', 'lunar', 'sky', 'wallpaper', 'wallpaper-dim',
  'ss-wallpaper', 'ss-dim', 'ss-glow'];

function makeDocument() {
  const doc = new Node('#document');
  doc.body = new Node('body', doc);
  doc.documentElement = new Node('html', doc);
  doc.hidden = false;
  const byId = {};
  for (const id of IDS) {
    byId[id] = new Node('div', doc);
    byId[id].attrs.id = id;
  }
  for (const id of HIDDEN) byId[id].hidden = true;
  doc.getElementById = (id) => byId[id] || null;
  doc.createElement = (tag) => new Node(tag, doc);
  doc.createElementNS = (ns, tag) => new Node(tag, doc);
  doc.createTextNode = (text) => { const n = new Node('#text', doc); n._text = String(text); return n; };
  doc.dispatch = (type, event) => (doc.listeners[type] || []).forEach((fn) => fn(event));
  return doc;
}

function memoryStorage(initial) {
  return {
    data: Object.assign({}, initial || {}),
    getItem(k) { return k in this.data ? this.data[k] : null; },
    setItem(k, v) { this.data[k] = String(v); }
  };
}

/**
 * Boot the launcher. options.bridge(uri, payload) -> answer object, or an array of answers for a subscription;
 * null means the platform never answers. options.baked: inventory.js data; options.theme: theme.js data.
 */
function boot(options) {
  const doc = makeDocument();
  const calls = [];
  const timers = new Map();
  let nextTimer = 1;
  const storage = options.storage || memoryStorage();
  class PalmServiceBridge {
    call(uri, payload) {
      const parsed = JSON.parse(payload);
      calls.push({ uri, payload: parsed, bridge: this });
      const answer = options.bridge ? options.bridge(uri, parsed) : { returnValue: false };
      const answers = answer === null ? [] : Array.isArray(answer) ? answer : [answer];
      const self = this;
      this.later = answers.slice(1);
      if (answers.length) Promise.resolve().then(() => self.onservicecallback(JSON.stringify(answers[0])));
    }
    cancel() { this.cancelled = true; }
  }
  const window = {
    document: doc,
    localStorage: storage,
    navigator: { language: options.language || 'en-US' },
    setTimeout: (fn, ms) => { const id = nextTimer++; timers.set(id, { fn, ms }); return id; },
    clearTimeout: (id) => { timers.delete(id); },
    addEventListener: () => {},
    location: { search: '' }
  };
  if (!options.notWebos) window.PalmServiceBridge = PalmServiceBridge;
  window.window = window;
  window.CYTV = {};
  if (options.baked !== undefined) window.CYTV.baked = options.baked;
  if (options.theme) window.CYTV.theme = options.theme;
  const ctx = vm.createContext(window);
  const skip = new Set(['js/inventory.js', 'js/theme.js']);   // generated at build time; tests pass the data directly
  for (const f of SCRIPTS) {
    if (skip.has(f)) continue;
    vm.runInContext(fs.readFileSync(path.join(LAUNCHER, f), 'utf8'), ctx, { filename: f });
  }
  const menuItems = () => doc.getElementById('menu-items').children;
  const api = {
    window, doc, calls, storage, timers,
    run(code) { return vm.runInContext(code, ctx); },
    async settle() { for (let i = 0; i < 10; i++) await Promise.resolve(); },
    key(code, opts) {
      opts = opts || {};
      const ev = { keyCode: code, repeat: !!opts.repeat, preventDefault() { this.prevented = true; } };
      doc.dispatch('keydown', ev);
      if (!opts.hold) doc.dispatch('keyup', { keyCode: code, preventDefault() {} });
      return ev;
    },
    /** Hold OK past the hold time, then release. */
    hold() {
      api.key(13, { hold: true });
      api.fire((t) => t.ms === 600);
      doc.dispatch('keyup', { keyCode: 13, preventDefault() {} });
    },
    /** Run (and drop) every pending timer the predicate picks. */
    fire(pick) {
      for (const [id, t] of [...timers]) if (pick(t)) { timers.delete(id); t.fn(); }
    },
    fireTimersAtLeast(ms) { api.fire((t) => t.ms >= ms); },
    focused() {
      for (const id of ['topbar', 'home']) {
        const stack = [doc.getElementById(id)];
        while (stack.length) {
          const n = stack.pop();
          if (/\bfocused\b/.test(n.className) && n.getAttribute('data-key')) return n.getAttribute('data-key');
          stack.push(...n.children);
        }
      }
      return null;
    },
    /** Tiles of Home in order, the dock row first; null for an empty dock slot. */
    tiles() {
      const out = [];
      for (const row of doc.getElementById('home').children) {
        for (const c of row.children) if (/\b(tile|slot)\b/.test(c.className)) out.push(c.getAttribute('data-key'));
      }
      return out;
    },
    dock() {
      const band = doc.getElementById('home').children[0];
      return band && /\bdock\b/.test(band.className) ? band.children.map((c) => c.getAttribute('data-key')) : [];
    },
    top() { return doc.getElementById('topbar').children.map((c) => c.getAttribute('data-key')); },
    launches() { return calls.filter((c) => c.uri.endsWith('/launch')).map((c) => c.payload.id); },
    notice() { return doc.getElementById('notice').hidden ? '' : doc.getElementById('notice').textContent; },
    menuOpen() { return !doc.getElementById('menu').hidden; },
    menuTitle() { return doc.getElementById('menu-title').textContent; },
    menuLabels() { return menuItems().map((c) => (c.children[0] ? c.children[0].textContent : c.textContent)); },
    menuStates() { return menuItems().map((c) => (c.children[1] ? c.children[1].textContent : '')); },
    /** Choose a menu item by its label with the remote: Up or Down until it is focused, then OK. */
    choose(label) {
      const labels = api.menuLabels();
      const want = labels.indexOf(label);
      if (want < 0) throw new Error(`no menu item ${label}: ${labels.join(', ')}`);
      let at = menuItems().findIndex((c) => /\bfocused\b/.test(c.className));
      while (at < want) { api.key(40); at++; }
      while (at > want) { api.key(38); at--; }
      api.key(13);
    }
  };
  return api;
}

module.exports = { boot, memoryStorage };
