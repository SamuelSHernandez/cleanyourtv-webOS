# Draft for the main project (not sent)

This is a local draft. Nothing has been posted, opened or sent upstream. The main project's policy
(`CONTRIBUTING.md`, "Where does my idea go?") routes ports to their own repository plus one `SHOWCASE.md` row,
so this asks for nothing else. It needs no change to the Android launcher and no change to any default.

## Splitting this folder into its own repository

1. Commit `webos/` on its branch, then run `git subtree split --prefix=webos -b webos-only`.
2. Push `webos-only` to a new repository's `main`. Its `.github/` then becomes active: CI runs tests only.
3. In the new repository, drop the `webos/` prefix from commands in the docs, for example
   `sed -i '' 's#webos/cytv-webos#./cytv-webos#g; s#webos/tests#tests#g; s#webos/scripts#scripts#g'` over
   `*.md`. `tests/test_docs.py` checks the commands still exist.

## Before proposing

- [ ] Split `webos/` into its own repository (`git subtree split --prefix=webos -b webos-only`), with its own
      issue tracker.
- [x] A run on a real TV, recorded in `profiles/` at `experimental-hardware`: LG 50UQ7570PUJ, webOS 22.
- [ ] The full [hardware-acceptance.md](hardware-acceptance.md) section A on that TV.
- [x] A screenshot from that TV (`themes/default/screenshot.jpg`, captured from the TV's engine; it shows no Wi-Fi
      name or account).

## Draft row, for the section "Other platforms: Fire TV and LG webOS"

| Project | What it is | Built on | By |
|---|---|---|---|
| [cleanyourtv-webOS](https://github.com/SamuelSHernandez/cleanyourtv-webOS) | **No root.** The webOS edition of this launcher for LG TVs in Developer Mode: the same Home model, theme keys, card rules and 28 languages, a dock-only mode, themes and a Night Clock add-on. Installed and removed with a journal that reads every result back from the TV. No network use on the TV; the Home button stays LG's | LG 50UQ7570PUJ, webOS 22 | *(GitHub handle)* |

## Short PR description, if a row is proposed

> SHOWCASE: add cleanyourtv-webOS (LG webOS, no root)
>
> One row in "Other platforms". The project lives in its own repository and changes nothing here.
> Tested on: LG 50UQ7570PUJ, webOS 22, firmware 04.60.91.
