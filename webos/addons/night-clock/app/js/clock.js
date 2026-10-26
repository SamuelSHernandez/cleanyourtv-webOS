/*
 * Night Clock: the time and date, drifting to a new place each minute and turning a dim amber late at night.
 * No network, no storage, no platform calls. Back (461) closes the app; webOS returns to what was open before.
 */
(function () {
  'use strict';
  var face = document.getElementById('face');
  var timeEl = document.getElementById('time');
  var dateEl = document.getElementById('date');
  var timer = null;
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
    'November', 'December'];

  function dateText(now) {
    try {
      if (typeof Intl !== 'undefined') {
        return new Intl.DateTimeFormat(navigator.language, { weekday: 'long', day: 'numeric', month: 'long' }).format(now);
      }
    } catch (e) { /* fall through to English */ }
    return DAYS[now.getDay()] + ' ' + now.getDate() + ' ' + MONTHS[now.getMonth()];
  }

  function tick() {
    var now = new Date();
    var h = now.getHours();
    var m = now.getMinutes();
    timeEl.textContent = (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    dateEl.textContent = dateText(now);
    document.body.className = h >= 23 || h < 6 ? 'late' : '';
    face.style.left = Math.round(120 + Math.random() * 1000) + 'px';
    face.style.top = Math.round(100 + Math.random() * 560) + 'px';
    timer = setTimeout(tick, (60 - now.getSeconds()) * 1000 + 50);
  }

  function stop() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop(); else if (timer === null) tick();
  });
  document.addEventListener('keydown', function (e) {
    if (e.keyCode === 461 || e.keyCode === 27) {
      e.preventDefault();
      try { window.close(); } catch (err) { /* the TV's own Back handling takes over */ }
    }
  });
  tick();
})();
