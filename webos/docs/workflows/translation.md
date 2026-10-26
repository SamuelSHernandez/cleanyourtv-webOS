# Workflow: Translations

**When to use this:** a language is missing, a string reads wrong, or upstream's translations changed.

The launcher's strings are the Android launcher's own (`launcher/js/i18n.js`, generated). A translation
therefore goes to upstream first, [Gathin23/cleanyourtv](https://github.com/Gathin23/cleanyourtv), so both
launchers say the same thing. Once it is merged there:

```sh
git clone https://github.com/Gathin23/cleanyourtv /tmp/cytv-upstream
python3 webos/scripts/import_upstream_strings.py /tmp/cytv-upstream
```

The script writes `launcher/js/i18n.js` with the upstream commit in its header. A new key the launcher needs
goes into `KEYS` in the script, and only if upstream has it.

Then run the JS tests: `tests/js/calendar.test.js` checks that every translation uses only the arguments the
code passes, and contains no markup.
