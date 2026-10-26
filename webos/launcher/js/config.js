/*
 * The launcher's settings: built-in defaults, overlaid by the theme baked into the package (theme.js), overlaid
 * by the few choices the owner makes in Launcher settings on the TV. Key names, meanings and defaults follow the
 * Android launcher's config.xml and themes/README.md, so a theme reads the same on both; keys that cannot work on
 * webOS are not in this schema and are ignored like any unknown key.
 *
 * As upstream: every key is optional; an unknown or wrongly typed key is ignored (and reported, never fatal);
 * a theme that is not an object is ignored as a whole. So a theme can never break Home.
 *
 * The schema between the markers is plain JSON: the build (cytv_webos/themes.py) and the docs generator read
 * it from this file, so there is one definition of every key.
 */
(function (root) {
  'use strict';

  var SCHEMA = /* SCHEMA-BEGIN */ {
    "dock_apps": {"type": "appIds", "default": ["netflix", "youtube.leanback.v4", "amazon", "com.disney.disneyplus-prod"], "doc": "The first apps on Home, in order: the dock row. Apps the TV lacks are skipped. Once the owner moves apps on the TV, the saved order wins"},
    "fill_dock": {"type": "bool", "default": true, "doc": "Fill the dock slots `dock_apps` leaves free with the first grid apps; `false` leaves them empty"},
    "hidden_apps": {"type": "appIds", "default": [], "doc": "Never shown as tiles (with `app_library`, the owner can add them back)"},
    "app_labels": {"type": "appLabels", "default": [], "doc": "A tile's name instead of the app's own, as `\"id=Name\"`"},
    "live_tv_package": {"type": "appId", "default": "", "doc": "The Live TV app for the Inputs menu's Live TV row; empty picks LG's own when the TV has it"},
    "columns": {"type": "int", "min": 1, "max": 8, "default": 4, "doc": "Tiles per row, the dock included", "onTv": true},
    "rows_below_dock": {"type": "int", "min": 0, "max": 3, "default": 0, "doc": "Grid rows left visible under the dock when Home opens"},
    "dock_title": {"type": "bool", "default": true, "doc": "The focused dock app's name in large type above the dock"},
    "dock_row": {"type": "bool", "default": true, "doc": "The dock as its own row with a band; `false` makes the dock apps the first tiles of one plain grid"},
    "always_show_names": {"type": "bool", "default": false, "doc": "Names under every tile, dimmed until focused; `false` shows only the focused tile's name"},
    "top_bar_apps": {"type": "appIds", "default": [], "doc": "Apps shown as round buttons with their logo in the top bar; they leave the grid"},
    "show_inputs_pill": {"type": "bool", "default": true, "doc": "The Inputs pill in the top bar"},
    "icon_only_buttons": {"type": "bool", "default": false, "doc": "Settings as a round icon button; Inputs keeps its label"},
    "dock_only": {"type": "bool", "default": false, "doc": "Home shows only `dock_apps` (and approved cards, and apps the owner adds back); every other app waits in the App library, whose pill is then always shown. Off by default"},
    "app_library": {"type": "bool", "default": false, "doc": "An App library pill after the last Home row: every app, add one to Home or take it off. The choices stay on the TV when a theme changes"},
    "module_cards": {"type": "bool", "default": true, "doc": "Show the cards of add-ons the owner approved (docs/specs/card.md); `false` turns the feature off"},
    "app_keys": {"type": "appKeys", "default": [], "doc": "Remote buttons that open an app while Home is in front, as `\"403:netflix\"` (webOS key codes: 403 red, 404 green, 405 yellow, 406 blue); `inputs`, `settings`, `livetv` or `library` in place of the app opens that instead"},
    "background_color": {"type": "color", "default": "#000000", "doc": "Colour behind everything"},
    "sky_intensity": {"type": "int", "min": 0, "max": 100, "default": 0, "doc": "Time-of-day backdrop: a dark gradient that follows the clock; 0 hides it"},
    "wallpaper": {"type": "bool", "default": true, "doc": "Show the theme's picture (`wallpaper.jpg` or its `wallpapers/` collection)", "onTv": true},
    "wallpaper_rotation_minutes": {"type": "int", "min": 0, "max": 1440, "default": 0, "doc": "Rotate the `wallpapers/` collection at this interval; 0 keeps one picture"},
    "wallpaper_order": {"type": "enum", "values": ["shuffle", "sequential"], "default": "shuffle", "doc": "How a collection advances: `shuffle` avoids repeating the current picture, `sequential` walks the folder in name order"},
    "wallpaper_dim": {"type": "int", "min": 0, "max": 90, "default": 0, "doc": "Black overlay over the wallpaper, in percent"},
    "wallpaper_captions": {"type": "bool", "default": false, "doc": "The shown picture's name, from `wallpapers/captions.txt` (`001.jpg<TAB>Dusk over the peaks`)"},
    "wallpaper_moods": {"type": "moods", "default": null, "doc": "A collection grouped by time of day: `{\"morning\": [...], \"evening\": [...], \"night\": [...]}`. Morning 07:00-12:00, evening until 18:30, night the rest (webOS gives the launcher no location for sun times)"},
    "dock_opacity": {"type": "int", "min": 30, "max": 100, "default": 100, "doc": "Opacity of the dock's band, in percent"},
    "dock_band": {"type": "bool", "default": true, "doc": "Draw the dock band; `false` leaves the tiles floating on the background"},
    "dock_glass": {"type": "bool", "default": false, "doc": "The dock band as light frosted glass"},
    "glass_style": {"type": "enum", "values": ["glass", "rim", "halo"], "default": "glass", "doc": "The focus highlight: `glass` (translucent with a sheen and rim), `rim` (the rim alone) or `halo` (the rim with a soft outer glow)"},
    "animations": {"type": "bool", "default": true, "doc": "Focus and tile motion", "onTv": true},
    "reduced_motion": {"type": "bool", "default": false, "doc": "Calmer motion for slow TVs: every animation 90 ms or less, no overshoot"},
    "focus_overshoot": {"type": "bool", "default": true, "doc": "The focused tile swings slightly past its size before settling"},
    "show_greeting": {"type": "bool", "default": true, "doc": "The greeting above the clock"},
    "greeting_name": {"type": "text", "max": 40, "default": "", "doc": "A name after the greeting, e.g. `\"Sam\"`"},
    "header_white": {"type": "bool", "default": false, "doc": "The date in full white instead of dimmed"},
    "date_below_clock": {"type": "bool", "default": false, "doc": "The date on its own line under the clock"},
    "shamsi_date": {"type": "bool", "default": false, "doc": "The Solar Hijri date above the Gregorian one"},
    "lunar_date": {"type": "bool", "default": false, "doc": "The lunisolar date under the Gregorian one, e.g. `LUNAR 13/9 · YEAR OF THE HORSE`"},
    "lunar_utc_offset": {"type": "int", "min": -1, "max": 14, "default": -1, "doc": "Hours east of UTC the lunar calendar is computed for: 7 Vietnamese, 8 Chinese; -1 picks 7 in Vietnamese and 8 otherwise"},
    "locale": {"type": "locale", "default": "", "doc": "The launcher's language as a tag (`\"vi\"`, `\"pt-BR\"`) instead of the TV's"},
    "home_idle_clock_minutes": {"type": "int", "min": 0, "max": 1440, "default": 0, "doc": "Minutes Home may sit untouched before the clock screensaver; any key returns. 0 is off", "onTv": true},
    "clock_glow": {"type": "bool", "default": true, "doc": "The clock screensaver's coloured glow; `false` for plain black (OLED)"},
    "clock_wallpaper": {"type": "bool", "default": false, "doc": "The clock screensaver over the wallpaper instead of black"},
    "clock_wallpaper_dim": {"type": "int", "min": 0, "max": 90, "default": 50, "doc": "How dark that wallpaper is behind the clock, in percent"}
  } /* SCHEMA-END */;

  var ID_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/;
  var FILE_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.(jpg|png)$/;
  var TARGETS = ['inputs', 'settings', 'livetv', 'library'];
  // Keys the launcher itself needs, and keys whose system meaning must survive: never mappable.
  var RESERVED_KEYS = [8, 13, 27, 33, 34, 37, 38, 39, 40, 461, 447, 448, 449, 1056, 1057];
  var MAX_LIST = 64;

  function check(spec, v) {
    switch (spec.type) {
      case 'bool': return typeof v === 'boolean';
      case 'int': return typeof v === 'number' && v % 1 === 0 && v >= spec.min && v <= spec.max;
      case 'color': return typeof v === 'string' && /^#[0-9A-Fa-f]{6}$/.test(v);
      case 'enum': return spec.values.indexOf(v) >= 0;
      case 'appId': return v === '' || (typeof v === 'string' && ID_RE.test(v));
      case 'text': return typeof v === 'string' && v.length <= spec.max && !/[\u0000-\u001f\u007f]/.test(v);
      case 'locale': return v === '' || (typeof v === 'string' && /^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8}){0,2}$/.test(v));
      case 'appIds':
        return list(v, function (x) { return typeof x === 'string' && ID_RE.test(x); });
      case 'appLabels':
        return list(v, function (x) {
          var m = typeof x === 'string' && /^([^=]+)=(.{1,40})$/.exec(x);
          return !!m && ID_RE.test(m[1]) && !/[\u0000-\u001f\u007f]/.test(m[2]);
        });
      case 'appKeys':
        return list(v, function (x) {
          var m = typeof x === 'string' && /^(\d{1,5}):(.+)$/.exec(x);
          if (!m) return false;
          var code = +m[1];
          return code > 0 && code < 65536 && RESERVED_KEYS.indexOf(code) < 0 && (TARGETS.indexOf(m[2]) >= 0 || ID_RE.test(m[2]));
        });
      case 'moods':
        if (v === null) return true;
        if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
        for (var k in v) {
          if (!Object.prototype.hasOwnProperty.call(v, k)) continue;
          if (['morning', 'evening', 'night'].indexOf(k) < 0) return false;
          if (!list(v[k], function (f) { return typeof f === 'string' && FILE_RE.test(f); })) return false;
        }
        return true;
      default: return false;
    }
  }

  function list(v, ok) {
    if (!Array.isArray(v) || v.length > MAX_LIST) return false;
    for (var i = 0; i < v.length; i++) if (!ok(v[i])) return false;
    return true;
  }

  function copy(v) {
    return v === null || typeof v !== 'object' ? v : JSON.parse(JSON.stringify(v));
  }

  function defaults() {
    var out = {};
    for (var k in SCHEMA) if (Object.prototype.hasOwnProperty.call(SCHEMA, k)) out[k] = copy(SCHEMA[k]['default']);
    return out;
  }

  /**
   * The effective config: defaults, then each valid theme key, then each valid on-TV override (only keys marked
   * onTv). Returns { config, ignored: [key...] } so the build and tests can report what a theme got wrong.
   */
  function resolve(theme, overrides) {
    var cfg = defaults();
    var ignored = [];
    if (theme !== null && theme !== undefined) {
      if (typeof theme !== 'object' || Array.isArray(theme)) {
        ignored.push('(theme is not an object)');
      } else {
        for (var k in theme) {
          if (!Object.prototype.hasOwnProperty.call(theme, k)) continue;
          if (SCHEMA.hasOwnProperty(k) && check(SCHEMA[k], theme[k])) cfg[k] = copy(theme[k]);
          else ignored.push(k);
        }
      }
    }
    if (overrides && typeof overrides === 'object') {
      for (var o in overrides) {
        if (Object.prototype.hasOwnProperty.call(overrides, o) && SCHEMA.hasOwnProperty(o) && SCHEMA[o].onTv && check(SCHEMA[o], overrides[o])) {
          cfg[o] = overrides[o];
        }
      }
    }
    return { config: cfg, ignored: ignored };
  }

  /** "id=Name" entries as a map. */
  function labels(entries) {
    var out = Object.create(null);
    for (var i = 0; i < entries.length; i++) {
      var at = entries[i].indexOf('=');
      out[entries[i].slice(0, at)] = entries[i].slice(at + 1);
    }
    return out;
  }

  /** "403:netflix" entries as a map from key code to target. */
  function keyMap(entries) {
    var out = Object.create(null);
    for (var i = 0; i < entries.length; i++) {
      var at = entries[i].indexOf(':');
      out[+entries[i].slice(0, at)] = entries[i].slice(at + 1);
    }
    return out;
  }

  var api = { SCHEMA: SCHEMA, check: check, defaults: defaults, resolve: resolve, labels: labels, keyMap: keyMap,
    TARGETS: TARGETS, RESERVED_KEYS: RESERVED_KEYS, ID_RE: ID_RE, FILE_RE: FILE_RE };
  root.CYTV = root.CYTV || {};
  root.CYTV.config = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
