# Source audit

Inspected 2026-10-26. Files were read only: nothing from these trees was run, and no TV was contacted.
"Claimed" means the project's docs say so. "Code" means a code path was traced. "Tests" means an automated
test exercises it. "Hardware" means a physical-TV report exists, with who reported it.

| Repository | Commit | Licence |
|---|---|---|
| [Gathin23/cleanyourtv](https://github.com/Gathin23/cleanyourtv) (main project) | `f592b6d2db0cfa0e28779660f25ff65386a5ff9b` | MIT |
| [Razdva122/clean-your-tv-lg-webos](https://github.com/Razdva122/clean-your-tv-lg-webos) | `d5804f6a7ce5d4eb35c0093ca19ae011e5a6df7f` | MIT (bundled ws, core-js: MIT; fonts: OFL; CA bundle: MPL-2.0; Qt GUI: LGPL-3.0) |
| [OmkarK97/webos-vibehack](https://github.com/OmkarK97/webos-vibehack) | `31a518aef23768067975f3ac2e464462a8046bab` | MIT (Outfit font: OFL 1.1) |
| [lasharor/cleanyourtv-WebOS](https://github.com/lasharor/cleanyourtv-WebOS) | `5667cd53e31d08e64518a2f50248d5bbd329dca0` | MIT (inputhook binary: GPL-3.0; ezinject: Zlib; theme images: no stated licence) |

**No code was copied from any of them.** What this project took is listed under "Ideas adopted" with the file
that carries each idea. [`../THIRD_PARTY.md`](../THIRD_PARTY.md) records the provenance.

## Main project: the engineering reference

**Contribution policy.** Checked in `CONTRIBUTING.md` ("Where does my idea go?") and in
`.github/maintainer/MAINTAINER.md`. A port to another platform belongs in its own repository, with one row in
`SHOWCASE.md`. Changes to the safety rules, CI or the Home-safety logic go to the maintainer. `SHOWCASE.md`
already lists the three webOS projects below, under "Other platforms". This work changes nothing upstream. It
lives under `webos/` in a fork, can be split into its own repository with `git subtree split --prefix=webos`,
and asks only for a showcase row (see [maintainer-note.md](maintainer-note.md)).

Patterns traced in code and carried over:

| Upstream | What it does | Here |
|---|---|---|
| `tools/recovery.py` | It records state before the first change, and the first record wins. It adds only names it has not seen. It validates a record before replaying it. It writes atomically and fsyncs. A corrupt record is never replaced. | `cytv_webos/journal.py`, `store.py`, `lifecycle.py` |
| `tools/restore.sh` | It replays the record. Without a record it falls back to enabling the whole list and warns. | This project does **not** fall back: with no journal, restore refuses (`test_without_a_journal_nothing_is_invented`). |
| `launcher/build-and-install.sh` | It starts the launcher (`am start -W`, "Status: ok") **before** touching the stock launcher. It treats an unanswered query after a mutation as an unknown outcome. It writes the rollback commands locally when the link is lost. | Install verifies installed, launched, running and foreground stages separately. Home routing is a separate command that requires confirmed readiness. A link lost mid-mutation is recorded as `unknown` and reconciled. |
| `TileRefresh.java` | It rebuilds tiles only when packages changed, and folds background changes into one rebuild. | `launcher/js/refresh.js` |
| `MemoryTrimPolicy.java` | It releases artwork only when Home is not visible. | `visibilitychange` stops the clock and resets key state. A web app gets no trim callback, so artwork release is a hardware-gated follow-up. |
| `CardFeature.java` | The first failure switches an optional feature off for the session, and the core keeps working. | There are no optional features yet. Inventory and preference failures degrade to a notice (`launcher.test.js`). |
| `docs/specs/card.md` | A module card is bound to the app's signing key. | Not ported. webOS has no equivalent signature identity a launcher can read (ADR). |
| `tests/test_launcher_handover.py`, `test_recovery_record.py` | Real scripts run against a fake TV that keeps state. | `tests/faketv.py`, and fake `ares-*` executables in `tests/test_cli.py` |

Upstream also runs optional helpers and timers: accessibility key services, a minute tick, a stats thread. Each
one is opt-in and stopped in `onPause`/`onStop`. So the rule this project follows is not "no timers". It is
"nothing runs while hidden, and nothing optional runs unless enabled".

## The webOS projects

### Razdva122/clean-your-tv-lg-webos (no-root and root editions)

- **Home (no-root).**
  - **Code:** a static ARM C relay (`native/prototype/relay.c`, `filter.c`) grabs the remote's evdev node (`EVIOCGRAB`). It writes every other event into a writable twin node, suppresses Home, and has a Node controller (`native/app/native.js`) launch the launcher. Return-from-app comes from an SSAP `getForegroundAppInfo` subscription (`native/app/screen-watch.js`).
  - **Watchdog:** a 400 ms heartbeat. The relay exits after 2 s of silence, and the controller kills it after 2.5 s without an ack. Releasing key-ups before ungrabbing is sound design.
  - **Tests:** `test_filter.c` covers the key filter. `test_relay_startup.c` covers only the startup gate. The main forwarding loop has no automated test.
  - **Hardware:** one maintainer TV, LG OLED55C3RLA on firmware 43.21.71. There are community reports for a C4 and others.
- **Emergency stop.**
  - **Code:** three short Home presses write a persistent `state/blocked` latch, and only a manual start clears it.
  - **Mismatch:** `docs/RECOVERY.md` says this "opens LG Home", but the code launches the launcher, and the next Home press then goes to LG. This was not confirmed.
- **Inventory.**
  - **Code:** SSAP `listLaunchPoints` from the computer at install, baked into the package (`cytv/tv.py`, `cytv/package.py`). On-TV refresh goes through its own helper service.
  - **Inferred:** the launcher never calls `applicationManager` for a list, which suggests a Developer Mode app is refused it.
- **Install.**
  - **Code:** SSH as `prisoner` on port 9922 (Paramiko), with an O_EXCL receipt, readback reconciliation and no blind retry (`cytv/state.py`, `cytv/operations.py`).
- **Concerns.**
  - TLS verification is off for SSAP.
  - A 28-permission SSAP key is copied to the TV, group-readable.
  - Several Luna service methods have no caller check.
  - Debug stall hooks ship in production.
  - Prebuilt `.ipk` files are committed.

### OmkarK97/webos-vibehack (no-root, external watcher)

- **Home.**
  - **Code:** `home-watch.py` on the computer subscribes to `getForegroundAppInfo` and launches the launcher when `com.webos.app.home` comes to the front. A second LG Home event within 3 s is taken as the owner choosing LG Home.
  - **Gaps:** there is no relaunch cap and no failure state. A redirect fires when the first snapshot shows LG Home. The launch answer is never checked. A launchd `KeepAlive` agent can re-prompt pairing in a loop.
  - **Tests:** none.
  - **Hardware:** README claim only (LG OLED C6, firmware 43.21.79).
- **Concerns.**
  - TLS verification is off.
  - The client key is written with default file permissions inside the repo folder.
  - It requests 28 permissions.
  - Icon URLs have no scheme check, so `file://` is followed.
  - `npx -y` and `pip` installs are unpinned.
  - The app id `com.gathin.tvhome` collides with the Android launcher's package name.

### lasharor/cleanyourtv-WebOS (rooted)

- **Home.**
  - **Code:** a root init.d script bind-mounts the launcher over LG Home's app folder, in RAM, then restarts `sam`. A newer "stand-in" path covers native Home apps.
  - **Recovery layers:** a `DISABLE` file that survives reboot, the Homebrew Channel failsafe, a helper-health watchdog that runs `undo-home.sh temp`, and an install check that reboots on failure.
  - **Tests:** the boot and Home scripts are never executed by tests (`tools/test/scripts.test.js` uses `--no-start`).
  - **Hardware:** maintainer LG OLED65G26LA (firmware 33.23.05), plus community reports.
- **Input.**
  - **Code:** a prebuilt GPL-3.0 `libinputhookpp.so` is injected into `lginput2` with `ezinject` every 30 s, with no backoff. It cannot be unloaded until reboot.
- **Debloat.**
  - **Code:** it stops services and bind-mounts stubs. When `/etc/hosts` is writable, it is edited in place, which contradicts the "RAM only" claim.
  - **Gaps:** there is no read-back check. Undo starts units without regard to their state before.
- **Concerns.**
  - The root helper's local HTTP API has no per-session authorization, and its origin check can be satisfied by content the TV can load. This is described here only as a class of problem. It should go to that project privately, as its `SECURITY.md` asks, not into a public issue.
  - Several LAN listeners.
  - Unsigned self-update.

## Ideas adopted, and where

| Idea | From | Here |
|---|---|---|
| Bake the TV's launch points (SSAP `listLaunchPoints`) into the package; fetch icons only from the TV itself, bounded | Razdva122, OmkarK97 | `cytv_webos/inventory.py`. Icons are files, not `data:` URLs, so the CSP stays `img-src 'self' file:`. |
| Probe the platform list at runtime anyway, and report which source was used | (new) | `launcher/js/adapter-webos.js` |
| Foreground subscription plus a second Home press as an escape | OmkarK97 | `cytv_webos/watcher.py`, with a redirect cap, a confirm timeout, a start-loop cap, the first snapshot ignored, and a persistent stop |
| A persistent stop latch that only an explicit action clears | Razdva122, lasharor | `cytv_webos/integration.py` (`stopped` and `failed` leave only through `resume`) |
| Profile decisions as data plus a pure decision function, with honest evidence levels | lasharor (`tvprofile.js`, `compat.json`) | `profiles/*.json`, `cytv_webos/profiles.py` |
| webOS repeats OK keydown without `e.repeat` | lasharor (`app/src/js/input.js`) | `launcher/js/keys.js` ignores any OK keydown while OK is down |
| Magic Remote OK can arrive as a key and as a click | OmkarK97 (flagged as uncertain) | `keys.js` click guard |
| Receipt before mutation, readback reconcile, no blind retry | Razdva122, upstream | `lifecycle.py` |

## Excluded, and why

- **Input grabbing and injection** (Razdva122's relay, lasharor's inputhook). A process that owns the remote must
  be proven on hardware before it ships. This release ships no native code and grabs nothing.
- **Root Home takeover, debloat and LS2 rewrites.** They are out of the default tier, and no root tier is
  implemented yet (ADR).
- **Developer Mode auto-renewal.** It is unconfirmed on unrooted TVs even in its own project, and it needs a
  network call to LG with the session token in the URL. This project documents renewal as a maintenance task
  instead.
- **Network features:** self-update, remote themes and compatibility lists, voice/AI, IPTV, wallpapers,
  notifications.
- **Prebuilt binaries, unlicensed images, and other projects' app ids.**
