# ADR 0002: The same launcher as upstream, where webOS allows it

- Status: accepted (2026-10-26)
- Evidence: Gathin23/cleanyourtv@f592b6d (`themes/README.md`, `res/values/config.xml`, `DockSlots.java`,
  `docs/specs/card.md`, string resources); this project's tests; a run on an LG 50UQ7570PUJ (webOS 22, firmware
  04.60.91, Chrome 87) recorded in `profiles/`.

## Context

Milestone 1 (ADR 0001) had its own Home model: a separate dock and an alphabetical grid. It had English strings
only, and no themes or add-ons. The goal is a webOS edition that reads as the same project as the Android
launcher, so its maintainer and users meet the same keys, words and behaviour.

## Decisions

1. **Upstream's Home model.**
   - Home is one ordered list whose first row is the dock (`columns` tiles), as `DockSlots`.
   - Ordering: `dock_apps` first, then cards, then the rest by name.
   - Move reorders that list, and the saved order wins afterwards.
   - `fill_dock` leaves empty slots when off.
   - Preferences version 1 (the old dock list) is migrated, not dropped.
2. **Upstream's keys, names and defaults.**
   - The schema in `launcher/js/config.js` is the subset of upstream keys that mean something on webOS, plus
     `dock_only` (decision 6).
   - Python reads the same schema from that file, between markers, so the build validator, the docs table and
     the launcher cannot disagree.
   - At runtime a bad key is ignored and reported, as upstream; the build refuses it.
3. **Upstream's translations, not new ones.** `launcher/js/i18n.js` is generated from upstream's resources (57
   strings, 28 languages through the same fallback chain). The UI uses only strings upstream has: Move,
   App library, Remove from Home, Launcher settings. No string here was machine-translated.
4. **Themes are baked at build time.** A running Developer Mode app cannot receive files. "Pushing" a theme
   means installing again, which is checked like any install. On-TV choices reset on a new theme, as upstream.
5. **Cards: upstream's fields, a different trust step.**
   - webOS lets a launcher read neither another app's files nor its signer.
   - So the owner approves a card on the computer, which shows the app id and the package SHA-256, and only
     approved cards are baked in.
   - The field rules and reserved names are upstream's, checked on both sides.
6. **`dock_only`, a new off-by-default key.** The owner of the first test TV wanted only three apps on Home and
   the rest out of sight. Upstream has no single key for it (`app_library` plus hiding each app lets new
   installs appear on Home). It is off by default, and a test shows that off changes nothing.
7. **CSP for `file://`.**
   - **Observed on the TV:** Chrome 87 treats the app's `file://` page as an opaque origin, so `'self'` blocked
     every script and the screen stayed black.
   - **Decision:** `script-src` and `style-src` allow `'self' file:`.
   - **Still blocked:** inline script, eval, remote hosts and every connection (`connect-src 'none'`).
8. **No Home-button interception in this project.** The Home button stays LG's:
   - the owner opens CYTV Home from the app bar or a Quick Access number key;
   - an external watcher exists as an experimental opt-in (ADR 0001), but it needs a computer, which the owner
     declined;
   - an on-TV watcher that only observes the foreground app is a separate investigation.

## Consequences

- A theme written for the Android launcher works here for every key both share. Android-only keys are ignored
  and listed in `themes/README.md`.
- **New strings have a dependency:** a new string waits for upstream (`docs/workflows/translation.md`).
- **Theme changes need a reinstall** of about ten seconds, recorded in the journal.
- **The journal now owns several apps** (the launcher and add-ons). Restore removes add-ons first and the
  launcher last, checking each removal.
