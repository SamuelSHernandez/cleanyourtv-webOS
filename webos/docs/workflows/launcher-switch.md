# Workflow: Add a launcher switch

**When to use this:** a small behaviour or look that is off by default and that a theme turns on.

1. Prefer the Android launcher's key when it has one: same name, same meaning, same default (its
   `themes/README.md` and `config.xml`). A webOS-only key needs a reason in the PR.
2. Add the key to the schema in `launcher/js/config.js`, between the `SCHEMA-BEGIN` and `SCHEMA-END` markers.
   Give it a type, a default (off for new behaviour) and `doc`. `onTv: true` only if Launcher settings offers it.
3. Implement it in the launcher. With the key off, nothing new may run: no timers, no listeners, no DOM.
4. Add `tests/js` cases for the key turned on, and one that shows the off state changes nothing.
5. Run `python3 webos/scripts/gen_docs.py` to regenerate the key table in `themes/README.md`.
6. Any new text must already exist in upstream's strings (`translation.md`). The schema and the Python
   validator (`cytv_webos/themes.py`) share one definition, so a new **type** needs both updated.
7. Run it on a real TV and attach `cytv-webos screenshot`.

Then run both test suites.
