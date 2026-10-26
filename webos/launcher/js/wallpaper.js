/*
 * Which picture Home shows. Pure: the page calls next() when the rotation timer fires, and current() for the
 * mood of the hour. Pictures are files baked into the package from the theme (art under wallpapers/), never URLs.
 *
 * As upstream: one wallpaper.jpg, or a wallpapers/ collection rotated every `wallpaper_rotation_minutes`, in
 * `shuffle` (never the same picture twice in a row) or `sequential` (name order, wrapping) order, optionally
 * grouped by `wallpaper_moods`. webOS gives a launcher no location, so moods use fixed hours.
 */
(function (root) {
  'use strict';

  function mood(hour, minute) {
    var t = hour * 60 + minute;
    if (t >= 7 * 60 && t < 12 * 60) return 'morning';
    if (t >= 12 * 60 && t < 18 * 60 + 30) return 'evening';
    return 'night';
  }

  /** The pictures to rotate through now: the mood's group when it has one, else every picture. */
  function pool(files, moods, now) {
    if (moods) {
      var group = moods[mood(now.getHours(), now.getMinutes())];
      if (group && group.length) {
        var out = [];
        for (var i = 0; i < group.length; i++) if (files.indexOf(group[i]) >= 0) out.push(group[i]);
        if (out.length) return out;
      }
    }
    return files.slice();
  }

  /** The next picture after `current`: sequential wraps in name order; shuffle avoids repeating current. */
  function next(files, current, order, random) {
    if (!files.length) return null;
    if (files.length === 1) return files[0];
    var sorted = files.slice().sort();
    if (order === 'sequential') {
      var at = sorted.indexOf(current);
      return sorted[(at + 1) % sorted.length];
    }
    var choices = [];
    for (var i = 0; i < sorted.length; i++) if (sorted[i] !== current) choices.push(sorted[i]);
    return choices[Math.floor(random() * choices.length) % choices.length];
  }

  /** "001.jpg<TAB>Dusk over the peaks" lines as a map; anything else is ignored. */
  function captions(text) {
    var out = {};
    if (typeof text !== 'string') return out;
    var lines = text.split(/\r?\n/);
    for (var i = 0; i < lines.length && i < 500; i++) {
      var m = /^([A-Za-z0-9][A-Za-z0-9._-]{0,63}\.(jpg|png))\t(.{1,80})$/.exec(lines[i]);
      if (m && !/[\u0000-\u001f\u007f]/.test(m[3])) out[m[1]] = m[3];
    }
    return out;
  }

  var api = { mood: mood, pool: pool, next: next, captions: captions };
  root.CYTV = root.CYTV || {};
  root.CYTV.wallpaper = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
