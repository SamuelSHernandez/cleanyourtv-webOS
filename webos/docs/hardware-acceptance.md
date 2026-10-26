# Hardware acceptance checklist

Run on a real TV with the real remote. `webos/cytv-webos screenshot --device tv` captures the launcher from the
TV's own engine, with its ready flag and timing marks; it opens LG's inspector for a few seconds and closes it. A browser preview, a simulator, an injected key or a passing test does
not count. Write down the model, firmware (Settings > Support > TV information), app version and backend. Do
not record or share serial numbers, MAC or IP addresses, Wi-Fi names, or account details. Blur them in
photos.

Before you start, have a way back: LG's app bar still works, and `cytv-webos restore` removes everything.

## A. Manual mode (no Home routing)

1. **Check.** `cytv-webos check` reports a profile, and lists `manual` as eligible.
2. **Install.** `cytv-webos install` reports these stages:
   - installed: yes
   - launched: yes
   - running: yes
   - foreground: yes (if paired)

   Answer the readiness question honestly.
3. **D-pad.**
   - From every edge of every section (shortcuts, dock, grid), press Up, Down, Left and Right. Focus moves
     predictably, never wraps, and never gets lost.
   - Hold a direction: focus keeps moving, and stops at the edge.
4. **OK and long press.**
   - A short OK opens the focused app, once.
   - Holding OK opens the tile menu and opens no app.
   - Each menu action does what it says: add, move left/right, remove, hide, show hidden.
5. **Magic Remote.**
   - Pointing focuses a tile. A click opens it once (watch for double launches).
   - Scrolling does nothing harmful.
6. **Back.** Back closes the menu. On the home screen it does nothing, and the launcher does not close.
7. **Leaving and returning.**
   - Open an app, then press Back: you return to the launcher, focused on the tile you left from.
   - Exit the app with its own menu: the result is noted.
8. **Shortcuts.** Inputs, Settings and Live TV each open LG's own screen. A shortcut the TV lacks is not shown.
9. **System keys are untouched.** Volume, Mute, Channel, Settings (gear), the Input button, Home, the number
   keys and the colour keys all keep their usual behaviour while the launcher is in front.
10. **HDMI and CEC.**
    - Switching inputs works.
    - CEC control of a soundbar or a player still works: volume through ARC/eARC, and power-on from the
      player.
11. **Standby.** After standby and wake, the launcher is either still there or relaunches from LG's app bar
    without errors.
12. **Cold boot.** Unplug the TV for 30 s. Repeat with Quick Start+ (Quick Start) on and off, and note what
    comes up first.
13. **Network.** With Wi-Fi off, the launcher still opens apps from its list, and loads no remote resource.
14. **Persistence.** Dock order and hidden apps survive closing the app, standby and a cold boot.
15. **Unavailable app.** Remove an app that is in the dock: its tile shows "not installed", and its menu offers
    removal.

## B. External watcher (experimental)

Needs A to pass first, plus `cytv-webos pair` and `cytv-webos confirm-ready`.

1. **Enable.** `home enable` refuses when another Home controller or Homebrew Channel is installed. Without
   one, it reports `activating`.
2. **Watch.** `home watch` running, open an app, then press Home. LG Home appears briefly, then the launcher.
   `home status` reports `active`.
3. **Escape.** Press Home again within 3 s: LG Home stays, until you open another app.
4. **Stop.**
   - `home stop` while the watcher runs: it exits within about 1 s, and Home stays LG Home.
   - Restart `home watch`: it exits at once and says it is stopped.
   - `home resume`, then `enable` again, brings routing back.
5. **Watcher crash.** Kill the watcher (`kill -9`): Home is LG Home, and the remote works normally.
6. **TV standby with the watcher running.** The watcher reports the TV as unreachable and retries, with backoff
   up to 60 s, without moving to `failed`. After wake, routing resumes.
7. **Developer Mode expired, or the app removed.** The watcher moves to `failed` with a reason, and stops
   launching.
8. **Network drop during a redirect.** `home status` shows `unknown`, then `activating` once the TV answers
   again.

## B2. Themes, Launcher settings and add-ons

1. **Themes.** `install --theme <name>` for each theme in `themes/`. Home changes as its row in
   `themes/README.md` says, and `screenshot` matches the theme's `screenshot.jpg`.
2. **Launcher settings.** Hold OK on Settings, then Launcher settings:
   - columns, animations, the clock and the wallpaper each apply at once;
   - Follow theme undoes them;
   - a new theme install undoes them too, and keeps the Move order.
3. **Move.** Hold OK on a tile, then Move: arrows move it through the dock and the grid, and Back twice ends.
   The order survives standby and a cold boot.
4. **App library** (`app_library` or `dock_only`):
   - Remove from Home and Add to Home work;
   - an app installed later stays off Home with `dock_only`.
5. **Clock screensaver.** With a clock time set: it appears after that idle time, moves every minute, and the
   key that wakes Home opens nothing.
6. **Add-on.** `addon install night-clock`, then `addon approve`, `sync` and `install`:
   - the card shows with its label and amber glow;
   - `addon remove` takes the add-on away and leaves the launcher.
7. **Languages.** Set the TV's language to one of the 28: Inputs, Settings and the greeting follow it.

## C. Update, rollback, uninstall

1. **Update.** Install a newer version over the old one: `installed` reads the new version, and readiness is
   asked again.
2. **Rollback.** Install the previous IPK with `--ipk`; it is recorded as a new install.
3. **Uninstall.** `restore`: the outcome is `restored_verified`. The app is gone from LG's app list, Home is LG
   Home, and `home status` reads `stopped`.
4. **Failed uninstall.** Run `restore` with the TV unreachable: the outcome is `unknown`, never
   `restored_verified`. The next `status` settles it.

## Measurements

Use the same TV, firmware and app list for every comparison, and repeat each measurement 5 times.

| Measure | How |
|---|---|
| Cold launcher start | `ares-inspect`, then `CYTV.metrics.ready - CYTV.metrics.scriptStart`, plus a phone video from the remote press to the first tile |
| Warm return to Home | Phone video: Home press (watcher) or Back from an app, to focused tile |
| Input to focus | `CYTV.metrics.lastKeyToFocusMs` (script time only) and a 240 fps phone video |
| App launch | Phone video: OK press to the app's first frame |
| Process memory | `ares-device --resource-monitor` (if supported), launcher in front and hidden |
| Hidden-state CPU | The same resource monitor, with another app in front for 5 minutes |
| Inventory refresh | `CYTV.metrics.lastBuildMs` after an app install, and `builds` (it should rise once per change) |
| Artwork | The size of `art/` in the IPK; memory with all tiles shown |

Report the results with the model, firmware, app version and checklist section. A maintainer moves a profile's
evidence level only from such a report.
