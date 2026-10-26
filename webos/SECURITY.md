# Security

## Reporting

Report a vulnerability privately with GitHub's "Report a vulnerability" (Security tab of this repository).
Do not open a public issue. Include the version, the TV model and firmware, and the steps. We aim to answer
within a week.

## What this project does to stay safe

| Area | What it does | Where |
|---|---|---|
| Launcher network | None. The CSP is `connect-src 'none'`, nothing remote loads, and the page has no fetch, XHR or WebSocket. A test enforces this. | `launcher/index.html`, `tests/js/static.test.js` |
| Platform calls | The page calls two constant Luna URIs (`launch`, `listLaunchPoints`) and launches only ids the adapter itself listed. There is no generic call, path or URL API. | `launcher/js/adapter-webos.js` |
| Themes and cards | Data only. Every key is validated by type; text goes in with `textContent`; pictures are checked by their bytes. No CSS, script or URL can come from a theme or a card. | `launcher/js/config.js`, `cytv_webos/themes.py`, `launcher/js/cards.js` |
| Packages | Verified before install: an ar/IPK of the expected id and version, architecture `all`, no ELF, no symlinks, nothing outside the app's folders, no preview files | `cytv_webos/build.py` |
| SSAP pairing | The six permissions the tools use; the TV certificate is pinned on first pairing and a change is refused until you re-pair on purpose; the client key is stored 0600 and never printed | `cytv_webos/ssap.py` |
| Commands | Every `ares-*` call is an argument array, never a shell string. App ids and device names are validated before use. | `cytv_webos/ares.py` |
| Records | Under `~/.cleanyourtv-webos` (0700 folder, 0600 files), written atomically; a corrupt record is never repaired or replaced automatically | `cytv_webos/store.py` |
| Reports and logs | Model, SDK and firmware only; IP and MAC addresses are removed from error text before it reaches a report or the journal | `cytv_webos/capabilities.py`, `cytv_webos/errors.py` |

## Known limits

- **Developer Mode access:** Developer Mode gives anyone holding its key (and passphrase) SSH access to the
  TV's Developer Mode jail. Keep `~/.ssh/tv_webos` private. Turn Key Server off after fetching the key.
- **Inspector tunnel:** `ares-inspect` (used by `cytv-webos screenshot`) listens on every network interface
  while it runs. The tool closes it within seconds.
- **SSAP permissions:** the SSAP client key can launch apps and read the app list on the TV for as long as the
  pairing lasts. Revoke it in the TV's settings if this computer is lost.
- **Hardware evidence:** see `profiles/` and `docs/compatibility.md` for what has run on a real TV.
