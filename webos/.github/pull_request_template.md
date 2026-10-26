<!-- Title: `area: what changed` (launcher, cytv, themes, addons, profiles, docs, tests). One topic per PR. -->

**What changed and why** (one or two sentences):

**Tested on:** <!-- TV model, webOS version, firmware (from `cytv-webos check`); or "not on a TV" and why -->

- [ ] `python3 -m unittest discover -s tests -t tests` passes
- [ ] `node --test 'tests/js/*.test.js'` passes
- [ ] `python3 scripts/gen_docs.py --check` passes
- [ ] New behaviour is off by default, and a test shows the off state changes nothing
- [ ] Visual change: a screenshot from a real TV (`cytv-webos screenshot`) is attached below
- [ ] No IP or MAC addresses, serials, Wi-Fi names, account names, keys or passphrases anywhere
- [ ] Theme or add-on: its folder has `screenshot.jpg` from a real TV; an add-on's README lists its Permissions
