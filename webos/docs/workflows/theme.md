# Workflow: Add a theme

**When to use this:** a new look that the keys in `themes/README.md` already carry.

1. Create `themes/<name>/config.json` using only keys from the table in `themes/README.md`.
   `themes/default/config.json` is the starting point.
2. Add `wallpaper.jpg`, `wallpaper.png` or a `wallpapers/` folder if it uses one. Pictures must be dark, at
   most 600 KB each, and art you have the right to use. Pictures drawn by a `make_*.py` script in the folder
   are best, as `aurora/` does.
3. Install it on a real TV and capture Home:
   ```sh
   webos/cytv-webos install --device tv --theme <name>
   webos/cytv-webos screenshot --device tv --out shot.png
   ```
4. Save `screenshot.jpg` from it: a JPEG at 1280x720, at most 300 KB, with the focus on the dock. Not a
   mock-up, not the preview.
5. Add the theme's line to `DESCRIPTIONS` in `scripts/gen_docs.py`, then run `python3 webos/scripts/gen_docs.py`.
   This regenerates the theme table in `themes/README.md`.
6. A look that needs a new key is a launcher switch first, in its own PR (`launcher-switch.md`).

Then run the tests: `python3 -m unittest discover -s webos/tests -t webos/tests`. `test_themes.py` fails without
the screenshot or with a README that is out of date.
