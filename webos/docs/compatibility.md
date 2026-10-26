# Compatibility and evidence

Passing `cytv-webos check` makes a TV **eligible** for a path; it does not mean the path works on that TV.
What has run on real hardware is listed here and in `profiles/`, tied to a model, firmware and app version.

## Hardware runs

| TV | webOS / SDK | Firmware | Engine | App | Backend | Level | What ran |
|---|---|---|---|---|---|---|---|
| LG 50UQ7570PUJ | webOS 22 / 7.6.0 | 04.60.91 | Chrome 87.0.4280.88 | 0.1.0 | manual | experimental-hardware | check, pair, sync, install (every stage), 5 themes, the Night Clock add-on, `dock_only`; navigation and launching tried by the owner with the remote |

The full [hardware checklist](hardware-acceptance.md) has not been run yet. Home routing has not run on hardware.

## Evidence levels

| Level | Means |
|---|---|
| `automated-tests-only` | Simulated TVs and a desktop browser only |
| `experimental-hardware` | Run on a TV by a developer of this project, without the full checklist |
| `community-reported` | Someone ran the checklist and reported it, unverified by a maintainer |
| `maintainer-verified` | A maintainer ran the checklist on that model and firmware with that app version |
| `known-incompatible` | Shown to fail, with the failure recorded |

A profile may claim a level for a backend only if it lists an evidence entry at that level
(`test_package.ProfileTest.test_no_hardware_claims_without_evidence`).

## What the tools detect, read-only

`cytv-webos check --device tv` collects only what a decision needs:

- **TV facts:** model, SDK version and firmware, from `ares-device --system-info`. Everything else the TV
  answers with (serial, MAC, OTA ids) is dropped (`test_report_keeps_private_identifiers_out`). Addresses are
  scrubbed from error text.
- **Profile:** the one covering the SDK major version. None means unsupported, and install refuses.
- **Tools:** the webOS CLI version, and any missing tools.
- **Installed apps:**
  - **source:** SSAP `listApps` when paired, else Developer Mode apps only (flagged as incomplete conflict
    detection);
  - **uses:** spotting other Home controllers and root setups, and resolving the Live TV and Settings
    shortcuts.
- **Home:** the selected backend and each backend's eligibility, with reasons.
- **Native code:** not applicable. Packages are architecture `all`, and the verifier refuses any ELF file.
- **Engine and readiness:** `cytv-webos screenshot` reads the engine (user agent), the ready flag and the timing
  marks from the running launcher.

## Support floor

| Item | Floor | Basis |
|---|---|---|
| webOS | SDK major 3 or later (`profiles/webos-devmode-generic.json`) | Eligibility only; proven on SDK 7.6 |
| Browser engine | Chromium 38 syntax and CSS (ES5; no custom properties, grid, gap or backdrop-filter) | `tests/js/static.test.js`. Proven on Chrome 87. No older engine has run it. |
| Computer | Python 3.9+, standard library; Node 18+ only for the JS tests | CI matrix (`.github/workflows/ci.yml`) |
| webOS CLI | `@webos-tools/cli` 3.2.6 | Used on the hardware run |

## Assumptions, and what the TV showed

| # | Assumption | On the 50UQ7570PUJ |
|---|---|---|
| 1 | A Developer Mode web app can launch other apps with `luna://com.webos.applicationManager/launch` | Confirmed (launched from tiles and the Inputs menu, by the owner) |
| 2 | `listLaunchPoints` is refused to Developer Mode apps | Confirmed: the app list came from install time |
| 3 | The page may load images from `file:///usr/palm/...` and its own package | Confirmed: all icons loaded (`icons` count in `screenshot`) |
| 4 | `'self'` in the CSP covers the app's own files | **Wrong.** The `file://` page is an opaque origin; every script was refused and the screen stayed black. Fixed with `file:` (ADR 0002). |
| 5 | SSAP accepts an unsigned manifest with six permissions | Confirmed; the pairing prompt was accepted |
| 6 | `getForegroundAppInfo` names the app in front | Confirmed, but empty for about a second after a launch; install asks again for up to 8 s |
| 7 | LG Home reports itself as `com.webos.app.home` | Not checked yet (needs the watcher) |
| 8 | `ares-install --listfull` prints `id :` / `version :` lines | Confirmed. With no Developer Mode apps it prints only `[Info] Set target device : tv`, which is now read as "none". Empty output still reads as "none": see C4 in the checklist. |
| 9 | Shortcut targets exist | Settings and Live TV yes. No separate input picker on webOS 22: the Inputs menu lists the TV's inputs itself (SSAP `getExternalInputList`). |

## Performance

These were measured on the 50UQ7570PUJ with `screenshot` (timing marks inside the page) and are
**single-sample observations, not budgets**:

- script start to ready: about 1.1 s with 30 tiles, and 1.3 s with 3;
- building Home: 228 ms (30 tiles) and 62 ms (3 tiles).

Budgets need repeated runs on the same TV ([checklist](hardware-acceptance.md#measurements)).
