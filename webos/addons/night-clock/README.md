# Night Clock

A calm, dim clock for the night: the time and date on black, moving to a new place every minute so nothing
stays lit in one spot, and turning a dim amber between 23:00 and 06:00. Back closes it.

It is its own webOS app. With its card approved, it shows on Home as **Night Clock** with the caption "A calm
clock for the night" and an amber glow.

```bash
webos/cytv-webos addon install --device tv night-clock    # install the app
webos/cytv-webos addon approve --device tv night-clock    # show its card on Home (asks you)
```

## Permissions

None. No `requiredACG`, no network (its CSP has `connect-src 'none'`), no storage, no platform calls, no
background service. It runs only while it is on screen.

Tested on: LG 50UQ7570PUJ, webOS 22, firmware 04.60.91.
