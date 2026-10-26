/*
 * Deterministic D-pad focus over the launcher's sections (shortcuts, dock, app grid).
 * Pure: no DOM. The same layout and key always give the same next focus.
 *
 * A section is { id, count, columns }. Focus is { section: index into sections, index }.
 * Left/Right stay inside a row and never wrap. Up/Down move a row inside a section, then to the
 * nearest non-empty section above or below, keeping the column where that row has one.
 */
(function (root) {
  'use strict';

  function rowsOf(section) {
    return Math.ceil(section.count / section.columns);
  }

  function rowLength(section, row) {
    var start = row * section.columns;
    return Math.max(0, Math.min(section.columns, section.count - start));
  }

  function nextNonEmpty(sections, from, step) {
    for (var s = from + step; s >= 0 && s < sections.length; s += step) {
      if (sections[s].count > 0) return s;
    }
    return -1;
  }

  /** The first focusable position, or null when every section is empty. */
  function first(sections) {
    var s = nextNonEmpty(sections, -1, 1);
    return s < 0 ? null : { section: s, index: 0 };
  }

  /** Clamp a focus to a layout that may have shrunk (an app removed, a section emptied). */
  function clamp(sections, focus) {
    if (!focus || !sections[focus.section] || sections[focus.section].count === 0) {
      if (focus && sections[focus.section]) {
        var below = nextNonEmpty(sections, focus.section, 1);
        if (below >= 0) return { section: below, index: 0 };
        var above = nextNonEmpty(sections, focus.section, -1);
        if (above >= 0) return { section: above, index: sections[above].count - 1 };
      }
      return first(sections);
    }
    var count = sections[focus.section].count;
    return { section: focus.section, index: Math.max(0, Math.min(focus.index, count - 1)) };
  }

  function move(sections, focus, direction) {
    focus = clamp(sections, focus);
    if (!focus) return null;
    var sec = sections[focus.section];
    var col = focus.index % sec.columns;
    var row = Math.floor(focus.index / sec.columns);
    if (direction === 'left') {
      return col > 0 ? { section: focus.section, index: focus.index - 1 } : focus;
    }
    if (direction === 'right') {
      return col < sec.columns - 1 && focus.index + 1 < sec.count
        ? { section: focus.section, index: focus.index + 1 } : focus;
    }
    if (direction === 'up') {
      if (row > 0) return { section: focus.section, index: focus.index - sec.columns };
      var up = nextNonEmpty(sections, focus.section, -1);
      if (up < 0) return focus;
      var upSec = sections[up];
      var lastRow = rowsOf(upSec) - 1;
      return { section: up, index: lastRow * upSec.columns + Math.min(col, rowLength(upSec, lastRow) - 1) };
    }
    if (direction === 'down') {
      if (row < rowsOf(sec) - 1) {
        return { section: focus.section, index: Math.min(focus.index + sec.columns, sec.count - 1) };
      }
      var down = nextNonEmpty(sections, focus.section, 1);
      if (down < 0) return focus;
      return { section: down, index: Math.min(col, rowLength(sections[down], 0) - 1) };
    }
    return focus;
  }

  var api = { first: first, clamp: clamp, move: move };
  root.CYTV = root.CYTV || {};
  root.CYTV.nav = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
