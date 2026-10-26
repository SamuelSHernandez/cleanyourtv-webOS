# Contributing

Thank you for helping. This is the LG webOS edition of [CleanYourTV](https://github.com/Gathin23/cleanyourtv). It
follows the main project's way of working: a small offline core, optional things kept optional, and nothing
claimed that a real TV has not shown.

## Where does my idea go?

| Your idea | Where it goes |
|---|---|
| A bug fix, a doc fix, a tool fix | A pull request |
| My TV works (or doesn't) | A device profile entry: [`docs/workflows/tv-profile.md`](docs/workflows/tv-profile.md) |
| A new look: colours, columns, wallpaper | A theme: [`docs/workflows/theme.md`](docs/workflows/theme.md) |
| A small launcher option | An off-by-default switch: [`docs/workflows/launcher-switch.md`](docs/workflows/launcher-switch.md) |
| A widget, a screensaver, a tool for the TV | An add-on: [`docs/workflows/addon.md`](docs/workflows/addon.md) |
| A translation | Upstream first: [`docs/workflows/translation.md`](docs/workflows/translation.md) |
| Network features in the launcher, root, intercepting the remote, a big redesign | Your own repository. Open an issue first if you are unsure. |

## Before you open a pull request

```sh
python3 -m unittest discover -s webos/tests -t webos/tests
node --test 'webos/tests/js/*.test.js'
python3 webos/scripts/gen_docs.py --check
```

- Fill in the PR template, including **Tested on** (TV model, webOS version, firmware).
- Anything visual has a screenshot from a real TV: `webos/cytv-webos screenshot --device tv`. A browser preview
  is welcome as well, but it does not replace the TV.
- One topic per pull request.
- No IP addresses, MAC addresses, serials, Wi-Fi names or account details anywhere.

## Testing on your TV

Developer Mode, `ares-cli` and a paired TV are described in [README.md](README.md). Your own experiments belong
in a theme folder of your own, outside this repo. `webos/cytv-webos restore --device tv` removes everything
this tool installed, and checks that it is gone.

## Reporting a security problem

Privately, as [SECURITY.md](SECURITY.md) describes. Never in a public issue.

Contributions are released under the repository's MIT licence.
