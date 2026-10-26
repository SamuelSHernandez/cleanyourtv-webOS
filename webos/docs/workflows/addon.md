# Workflow: Add an add-on

**When to use this:** a widget, tile or screen that can be its own small app, shown on Home through a card.

1. Create `addons/<name>/app/` as a webOS web app with its own id (`appinfo.json`, `index.html`, `js/`,
   `css/`):
   - ES5, no build step;
   - a CSP like the launcher's;
   - `connect-src 'none'` unless it truly needs the network, in which case say so in the README and expect a
     separate review.

   Icons named in `appinfo.json` and missing from the folder are drawn at build time.
2. Optionally add `addons/<name>/card.json` (`docs/specs/card.md`).
3. Write `addons/<name>/README.md`:
   - what it does;
   - `## Permissions`, listing every `requiredACG`, any network use and any background service (or "None");
   - a `Tested on:` line.
4. Install it on a real TV and capture it:
   ```sh
   webos/cytv-webos addon install --device tv <name>
   webos/cytv-webos screenshot --device tv --app <its app id> --out shot.png
   ```
   Save `screenshot.jpg` (JPEG, 16:9, at most 300 KB).
5. Add a row to the table in `addons/README.md`.
6. Nothing under `launcher/` changes, and the launcher never names an add-on. If the idea needs a launcher
   change, it is a switch or an issue, not an add-on.

Then run the tests: `python3 -m unittest discover -s webos/tests -t webos/tests` (`test_addons.py` checks all
of this).
