# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Gemini CLI, Cursor, Copilot and others) working in this
repository, the LG webOS edition of CleanYourTV. People should start with [README.md](README.md) and
[CONTRIBUTING.md](CONTRIBUTING.md); this file repeats their rules in the form an agent needs. It follows the
main project's AGENTS.md ([Gathin23/cleanyourtv](https://github.com/Gathin23/cleanyourtv)) wherever webOS allows.

## First: which job are you doing?

| You were asked to | Do this |
|---|---|
| Set up a TV: install the launcher, a theme, an add-on | Follow [README.md](README.md), "Install on a TV", on the real TV. Use `cytv-webos` rather than writing new tools. The only files you change are the person's own theme folder (outside this repo) and nothing else. Do not open issues or pull requests unless the person asks. |
| Change this repo: a fix, a theme, an add-on, a translation, docs | Read on from [Repo map](#repo-map). |

### Setting up a TV: the rules that are not negotiable

- **No root, nothing flashed, nothing uninstalled that this tool did not install.** Developer Mode only. Every
  change goes through `cytv-webos`, whose journal records the state before it and whose `restore` undoes it.
- **Never touch the TV without the person's go-ahead.** Read-only `check` first. Install, Home routing and
  anything else that changes the TV need their agreement for that TV.
- **Install changes nothing about Home.** The launcher is opened from LG's app bar until the person asks for
  more. Home routing (`home enable`) needs the launcher's readiness confirmed by a person
  (`confirm-ready`), and only one Home controller may ever be active.
- **Credentials are the person's to type.** The Developer Mode passphrase and anything like it: ask them to
  run the command themselves (`! ares-novacom --device tv --getkey`). The SSAP pairing prompt is accepted on
  the TV by them.
- **Stop and say so** when the TV refuses: a refused key, a failed install, an outcome `unknown` or
  `recovery_incomplete`. Run `cytv-webos status`; never retry in a loop, never report a refused or unknown
  outcome as done.
- **Close what you open.** `cytv-webos screenshot` closes LG's inspector tunnel itself. If you run
  `ares-inspect` by hand, close it at once: it listens on the whole network.
- **No private identifiers** anywhere you write: no IP addresses (use `192.168.1.50`), MAC addresses, serial
  numbers, Wi-Fi names, account names, keys or passphrases.

## Repo map

| Path | What it is |
|---|---|
| `launcher/` | The webOS web app: ES5, no build step, strict CSP, no network. `js/config.js` holds the key schema. |
| `cytv_webos/` | The computer-side tool `cytv-webos` (Python 3.9+, standard library only) |
| `themes/` | One folder per theme: `config.json`, a required real-TV `screenshot.jpg`, optional pictures. Keys in `themes/README.md` (generated) |
| `addons/` | One folder per add-on: its own webOS app, `card.json`, `README.md` with Permissions, real-TV `screenshot.jpg` |
| `profiles/` | Device profiles with hardware evidence levels |
| `preview/` | The launcher in a desktop browser with invented apps; never packed |
| `scripts/` | `import_upstream_strings.py` (translations), `gen_docs.py` (generated tables) |
| `tests/` | Python `unittest` (fake TV, fake `ares-*`) and `tests/js/` (`node --test`, fake DOM and platform) |
| `docs/` | ADRs, the card spec, compatibility, recovery, hardware checklist, source audit, [workflows](#workflows) |

## Where a change goes

| The change | Where it goes |
|---|---|
| A fix, a translation, docs, a tool fix, a device profile | A pull request here |
| A small launcher switch that is off by default | A pull request here: [`docs/workflows/launcher-switch.md`](docs/workflows/launcher-switch.md) |
| A new look that existing keys can carry | `themes/<name>/`: [`docs/workflows/theme.md`](docs/workflows/theme.md) |
| A widget or tile that can be its own small app | `addons/<name>/`: [`docs/workflows/addon.md`](docs/workflows/addon.md) |
| Network access in the launcher, root features, input interception, a changed default for every TV | Not here. Open an issue first. |
| Recovery logic, the journal, Home routing, the CSP, the launch allowlist | Open an issue for the maintainer; do not change them in a drive-by PR |

## Workflows

- [`theme.md`](docs/workflows/theme.md): add a theme from existing keys, with its screenshot from a real TV.
- [`addon.md`](docs/workflows/addon.md): add an add-on app with a module card.
- [`launcher-switch.md`](docs/workflows/launcher-switch.md): add an off-by-default key to the schema.
- [`translation.md`](docs/workflows/translation.md): strings come from upstream; how to refresh them.
- [`tv-profile.md`](docs/workflows/tv-profile.md): record a TV's hardware evidence in a profile.

## Before opening a PR

| Check | Command or rule |
|---|---|
| Python tests | `python3 -m unittest discover -s webos/tests -t webos/tests` |
| JS tests | `node --test 'webos/tests/js/*.test.js'` |
| Generated docs | `python3 webos/scripts/gen_docs.py --check` (the tests run it too) |
| Package | `webos/cytv-webos build` succeeds and prints a sha256 |
| Real TV | Launcher, Home and install changes run on a real TV: say which model and firmware in the PR's "Tested on" line, and attach `cytv-webos screenshot` for visual changes |
| One topic per PR | A theme, an add-on, a switch and a fix are separate PRs |

## Hard rules

- **No network in the launcher:** no `connect-src`, no remote URLs, no analytics, no polling. Add-ons that need
  the network say so in their Permissions section and are reviewed on their own.
- **No new defaults for every TV.** A new key is off by default; `tests/js` must show the off state changes
  nothing.
- **No generic platform calls from the page.** The adapter calls two constant Luna URIs and launches only ids
  it listed. Do not add a way to call arbitrary services, paths or URLs.
- **No prebuilt binaries, no bundled third-party art or fonts, no ELF in a package** (the verifier refuses one).
- **Strings come from upstream.** A new UI string needs upstream to have it first (or a discussion here).
- **No secrets or identifiers** in commits, profiles, screenshots or docs.
- **Never report success you did not read back.** The journal's outcomes are the vocabulary: `applied_verified`,
  `failed`, `refused`, `unknown`, `restored_verified`, `recovery_incomplete`.

## Commit and PR style

Titles are `area: what changed`, in plain words, with the issue in parentheses when there is one:
`launcher: dock_only, Home with only the dock apps`, `themes: add night`, `cytv: reconcile an update that never
landed`. The area is the folder: `launcher`, `cytv`, `themes`, `addons`, `profiles`, `docs`, `tests`.
