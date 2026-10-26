# ADR 0001: A small no-root core, with Home routing as a separate, swappable backend

- Status: accepted for milestone 1 (2026-10-26)
- Evidence: [source-audit.md](../source-audit.md) (four repositories at pinned commits) and this
  project's tests. **There is no physical-TV evidence yet.**

## Context

LG webOS has no supported way for a third-party app to become Home. The three existing webOS projects
reach Home in three ways:

- a native evdev relay that grabs the remote (no root);
- an external watcher that relaunches the launcher when LG Home comes to the front (no root);
- bind mounts by a root init script.

Each comes with a different failure boundary. Each also mixes the launcher, the Home routing, the installer
and, in two of them, a growing set of networked features. The main project's discipline is a small core,
effects that are verified, recovery recorded before mutation, and optional behaviour that stays inert when
off. A port has to carry that discipline without copying Android mechanics such as package disabling or
`set-home-activity`.

## Decision

1. **The launcher is a web app with no build step.**
   - ES5 source, so the syntax floor is Chromium 38 (webOS 3.x). A strict CSP; no remote resources and no
     network APIs.
   - It works on its own, launched by hand from LG's app bar. Installing it changes nothing about Home.
2. **The platform adapter is narrow.**
   - Five operations: capabilities, list apps, launch a listed id, open a resolved shortcut, and be told
     when the app list changes.
   - Exactly two Luna URIs, both constants. There is no generic Luna, path or URL API. A test enforces this.
   - The app list is probed live once. When the platform refuses, the launcher falls back to the list baked
     in at install, and it says which source it used.
3. **The computer does everything that changes the TV.** That is a Python CLI using only the standard
   library:
   - **Install transport:** LG's own webOS CLI (`ares-*`), called with argument arrays.
   - **Read and launch:** SSAP, using the smallest permission set and a pinned certificate.
   - **State:** every mutation goes through the journal (baseline, intent, one outcome, reconcile).
4. **Home routing is a separate state machine with one owner at a time.**
   - States: `inactive`, `activating`, `active`, `unknown`, `failed`, `stopped`.
   - Install never touches it.
   - Activation requires the launcher's readiness to have been confirmed by a person, for the installed
     version.
   - Only `resume` leaves `stopped` or `failed`.
   - Backends: `manual` (the default) and `external-watcher` (experimental).
5. **The first Home backend is the external watcher.** It is the only one of the three whose worst failure is
   bounded without trusting a process on the TV. It never touches input devices. If it hangs, the TV is
   stock. Its only possible misbehaviour, redirecting when the owner wanted LG Home, is capped by:
   - a passthrough on a second Home press;
   - a redirect-rate cap;
   - a confirm-timeout cap;
   - a cap on process starts;
   - a persistent stop that a restarted watcher obeys.
6. **Device differences are data:** `profiles/*.json` is versioned and validated, and every backend carries
   an evidence level. A profile makes a TV *eligible*; it never certifies it.

## Not done, on purpose

- **On-TV no-root helper (input grab).** It would be the better user experience: no computer needed, and Home
  never flashes LG Home. But it needs native code per firmware family, a watchdog that lives outside the
  grabbing process, and hardware proof that key release, long press and repeat survive a helper crash. It
  waits for a TV.
- **Root tier.** This would be a separate, opt-in package for TVs that are already rooted. The root package
  would:
  - never obtain root itself;
  - detect Homebrew Channel and other Home controllers;
  - make each cleanup separately selectable, with its prior state recorded and restored on return to LG Home.

  Not started.
- **Module cards.** Upstream binds a card to an Android signing key. webOS gives a launcher no comparable
  identity for another app, so there is nothing safe to bind to yet.
- **Developer Mode renewal.** This is documented as a maintenance task. Nothing in this release renews the
  session or depends on a renewal.

## Consequences

- **Developer Mode expiry.** When the session expires, the TV removes Developer Mode apps. The launcher then
  disappears and the watcher moves to `failed` ("the launcher is not installed"). Nothing breaks LG Home.
- **Watcher redirects.** With the watcher, pressing Home shows LG Home briefly before the launcher. That is
  the cost of not grabbing input.
- **Stale app list.** When the live list is refused, an app installed later appears only after `sync`, then
  `build`, then `install`.
- **Repository layout.** Everything lives under `webos/`, so it can become its own repository with
  `git subtree split --prefix=webos`, as the main project's policy asks of ports. Nothing outside `webos/` is
  changed.
