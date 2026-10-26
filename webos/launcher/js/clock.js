/*
 * The header's words and numbers: greeting, time, date, the Solar Hijri and lunisolar dates, and the colour of
 * the time-of-day sky. Pure; `now` is passed in.
 *
 * Greeting hours, toJalali() and the lunar calendar are ported from the Android launcher
 * (Gathin23/cleanyourtv@f592b6d, MainActivity.java greeting, Shamsi.java and Lunar.java; MIT, Copyright (c)
 * 2026 Gathin). The lunar astronomy is Hồ Ngọc Đức's public algorithm, as upstream's header says.
 */
(function (root) {
  'use strict';

  var SHAMSI = ['farvardin', 'ordibehesht', 'khordad', 'tir', 'mordad', 'shahrivar', 'mehr', 'aban', 'azar',
    'dey', 'bahman', 'esfand'];

  function greetingKey(hour, lang) {
    if (lang === 'da') {   // Danish day parts: "God morgen" until 11, then "God formiddag" to noon.
      if (hour < 5) return 'good_night';
      if (hour < 11) return 'good_morning';
      if (hour < 12) return 'good_forenoon';
      if (hour < 18) return 'good_afternoon';
      return hour < 22 ? 'good_evening' : 'good_night';
    }
    if (hour < 5) return 'good_night';
    if (hour < 12) return 'good_morning';
    if (hour < 17) return 'good_afternoon';
    return hour < 22 ? 'good_evening' : 'good_night';
  }

  function greeting(strings, now, name) {
    var text = strings.t(greetingKey(now.getHours(), strings.lang.split('-')[0]));
    return name ? strings.t('greeting_with_name', text, name) : text;
  }

  function time(now) {
    var h = now.getHours();
    var m = now.getMinutes();
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  /** "Monday 26 October" in the launcher's language; English names when the engine has no Intl for it. */
  function date(now, lang) {
    try {
      if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
        return new Intl.DateTimeFormat(lang, { weekday: 'long', day: 'numeric', month: 'long' }).format(now);
      }
    } catch (e) { /* an engine without this locale: fall through */ }
    var days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
      'November', 'December'];
    return days[now.getDay()] + ' ' + now.getDate() + ' ' + months[now.getMonth()];
  }

  function div(a, b) {
    return Math.floor(a / b);
  }

  /** Gregorian to Jalali, the 33-year-cycle algorithm (upstream Shamsi.toJalali). Returns [year, month, day]. */
  function toJalali(gy, gm, gd) {
    var monthStart = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var gy2 = gm > 2 ? gy + 1 : gy;
    var days = 355666 + 365 * gy + div(gy2 + 3, 4) - div(gy2 + 99, 100) + div(gy2 + 399, 400) + gd + monthStart[gm - 1];
    var jy = -1595 + 33 * div(days, 12053);
    days %= 12053;
    jy += 4 * div(days, 1461);
    days %= 1461;
    if (days > 365) {
      jy += div(days - 1, 365);
      days = (days - 1) % 365;
    }
    var jm;
    var jd;
    if (days < 186) {
      jm = 1 + div(days, 31);
      jd = 1 + days % 31;
    } else {
      jm = 7 + div(days - 186, 30);
      jd = 1 + (days - 186) % 30;
    }
    return [jy, jm, jd];
  }

  function shamsi(strings, now) {
    var j = toJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
    return j[2] + ' ' + strings.t('shamsi_month_' + SHAMSI[j[1] - 1]) + ' ' + j[0];
  }

  // ---- lunisolar calendar (upstream Lunar.java) ---------------------------------------------------------------

  function jdFromDate(dd, mm, yy) {
    var a = div(14 - mm, 12);
    var y = yy + 4800 - a;
    var m = mm + 12 * a - 3;
    var jd = dd + div(153 * m + 2, 5) + 365 * y + div(y, 4) - div(y, 100) + div(y, 400) - 32045;
    if (jd < 2299161) jd = dd + div(153 * m + 2, 5) + 365 * y + div(y, 4) - 32083;
    return jd;
  }

  function newMoonDay(k, tz) {
    var t = k / 1236.85;
    var t2 = t * t;
    var t3 = t2 * t;
    var dr = Math.PI / 180;
    var jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3;
    jd1 += 0.00033 * Math.sin((166.56 + 132.87 * t - 0.009173 * t2) * dr);
    var m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3;
    var mpr = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3;
    var f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3;
    var c1 = (0.1734 - 0.000393 * t) * Math.sin(m * dr) + 0.0021 * Math.sin(2 * dr * m);
    c1 = c1 - 0.4068 * Math.sin(mpr * dr) + 0.0161 * Math.sin(dr * 2 * mpr);
    c1 = c1 - 0.0004 * Math.sin(dr * 3 * mpr);
    c1 = c1 + 0.0104 * Math.sin(dr * 2 * f) - 0.0051 * Math.sin(dr * (m + mpr));
    c1 = c1 - 0.0074 * Math.sin(dr * (m - mpr)) + 0.0004 * Math.sin(dr * (2 * f + m));
    c1 = c1 - 0.0004 * Math.sin(dr * (2 * f - m)) - 0.0006 * Math.sin(dr * (2 * f + mpr));
    c1 += 0.0010 * Math.sin(dr * (2 * f - mpr)) + 0.0005 * Math.sin(dr * (2 * mpr + m));
    var deltaT = t < -11
      ? 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
      : -0.000278 + 0.000265 * t + 0.000262 * t2;
    return Math.floor(jd1 + c1 - deltaT + 0.5 + tz / 24);
  }

  function sunLongitude(jdn, tz) {
    var t = (jdn - 2451545.5 - tz / 24) / 36525;
    var t2 = t * t;
    var dr = Math.PI / 180;
    var m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2;
    var l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2;
    var dl = (1.914600 - 0.004817 * t - 0.000014 * t2) * Math.sin(dr * m);
    dl += (0.019993 - 0.000101 * t) * Math.sin(dr * 2 * m) + 0.000290 * Math.sin(dr * 3 * m);
    var l = (l0 + dl) * dr;
    l -= Math.PI * 2 * Math.floor(l / (Math.PI * 2));
    return Math.floor(l / Math.PI * 6);
  }

  function lunarMonth11(yy, tz) {
    var off = jdFromDate(31, 12, yy) - 2415021;
    var k = Math.floor(off / 29.530588853);
    var nm = newMoonDay(k, tz);
    if (sunLongitude(nm, tz) >= 9) nm = newMoonDay(k - 1, tz);
    return nm;
  }

  function leapMonthOffset(a11, tz) {
    var k = Math.floor((a11 - 2415021.076998695) / 29.530588853 + 0.5);
    var i = 1;
    var arc = sunLongitude(newMoonDay(k + i, tz), tz);
    var last;
    do {
      last = arc;
      i++;
      arc = sunLongitude(newMoonDay(k + i, tz), tz);
    } while (arc !== last && i < 14);
    return i - 1;
  }

  /** Gregorian date to [day, month, year, leap] of the lunar calendar at UTC+tz. */
  function fromSolar(dd, mm, yy, tz) {
    var dayNumber = jdFromDate(dd, mm, yy);
    var k = Math.floor((dayNumber - 2415021.076998695) / 29.530588853) + 1;
    var monthStart = newMoonDay(k, tz);
    while (monthStart > dayNumber) monthStart = newMoonDay(--k, tz);
    var a11 = lunarMonth11(yy, tz);
    var b11 = a11;
    var lunarYear;
    if (a11 >= monthStart) {
      lunarYear = yy;
      a11 = lunarMonth11(yy - 1, tz);
    } else {
      lunarYear = yy + 1;
      b11 = lunarMonth11(yy + 1, tz);
    }
    var lunarDay = dayNumber - monthStart + 1;
    var diff = Math.floor((monthStart - a11) / 29);
    var leap = 0;
    var lunarMonth = diff + 11;
    if (b11 - a11 > 365) {
      var leapDiff = leapMonthOffset(a11, tz);
      if (diff >= leapDiff) {
        lunarMonth = diff + 10;
        if (diff === leapDiff) leap = 1;
      }
    }
    if (lunarMonth > 12) lunarMonth -= 12;
    if (lunarMonth >= 11 && diff < 4) lunarYear -= 1;
    return [lunarDay, lunarMonth, lunarYear, leap];
  }

  function mod(a, n) {
    return ((a % n) + n) % n;
  }

  function lunar(strings, now, offset) {
    var tz = offset >= 0 ? offset : strings.lang.split('-')[0] === 'vi' ? 7 : 8;
    var l = fromSolar(now.getDate(), now.getMonth() + 1, now.getFullYear(), tz);
    var month = l[3] === 1 ? strings.t('lunar_month_leap', l[1]) : String(l[1]);
    var stems = strings.list('lunar_stems');
    var branches = strings.list('lunar_branches');
    var year = strings.t('lunar_year', stems[mod(l[2] + 6, 10)], branches[mod(l[2] + 8, 12)]);
    return strings.t('lunar_date_format', l[0], month, year);
  }

  /** The sky behind Home for an hour of the day: [top colour, bottom colour] as #RRGGBB. */
  function sky(hour) {
    if (hour < 5 || hour >= 21) return ['#0b1026', '#000000'];
    if (hour < 7) return ['#2b2f5a', '#5a3a4a'];
    if (hour < 17) return ['#1d3b66', '#0b1a2e'];
    if (hour < 19) return ['#4a2c4f', '#1a1030'];
    return ['#1a1838', '#05050c'];
  }

  var api = { greetingKey: greetingKey, greeting: greeting, time: time, date: date, toJalali: toJalali, shamsi: shamsi,
    fromSolar: fromSolar, lunar: lunar, sky: sky };
  root.CYTV = root.CYTV || {};
  root.CYTV.clock = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
