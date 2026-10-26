# Module card on webOS, spec 1

An add-on (a separate webOS app) can show a **card** on Home: its tile with a label of its choice, an optional
caption and an optional glow colour, placed after the dock apps and before the alphabetical grid.

The card's **fields and rules are the Android launcher's spec 1** (Gathin23/cleanyourtv `docs/specs/card.md`):
the same field names, lengths, character set, reserved names, and limits. What differs is **how the launcher
learns about a card, and who decides**, because webOS gives a Developer Mode launcher neither of the two things
the Android design relies on:

| Android (upstream) | webOS (here) |
|---|---|
| The launcher reads the card from the app's manifest through the package manager | The launcher cannot read another app's files. The card ships in the add-on's folder as `card.json`. |
| The owner decides on the TV, and the decision is bound to the app's signing key | webOS exposes no signing identity a launcher can check. The owner decides on the computer (`cytv-webos addon approve`), where the app id, the card and the package's SHA-256 are shown, and only approved cards are baked into the launcher. |

## Declaration: `addons/<name>/card.json`

```json
{ "spec": 1, "label": "Night Clock", "caption": "A calm clock for the night", "accent": "#E8A33D" }
```

| Field | Required | Rule |
|---|---|---|
| `spec` | yes | `1`. Anything else: no card. |
| `label` | yes | 1 to 24 characters from `A-Z a-z 0-9` space `. & + ' -`, no leading or trailing space, at least one letter or digit |
| `caption` | no | Up to 32 characters from the same set |
| `accent` | no | `#RRGGBB`: the focus ring and glow while the card is focused |

No other fields. Text is plain text; the launcher puts it on screen with `textContent`.

## Reserved names

Labels are compared folded: lower case, ASCII letters and digits only, so "Live TV", "live-tv" and "LIVETV"
are the same name. A label is refused when:

- it contains `verified` or `official` anywhere (the caption may not either);
- it is a name the launcher's own UI uses, in English or in the TV's language: Home, Settings, Inputs, Wi-Fi,
  Live TV, App library, Launcher settings, Choose default home, Default home, Clock, and the project names
  `cleanyourtv` and `tv-vibehack`;
- it starts with `HDMI`, or it is `AV`;
- at approval, it equals the name of another app on the TV;
- two shown cards fold to the same label: the older decision keeps it, the newer card is dropped.

## Decision record

The decisions live in `~/.cleanyourtv-webos/<device>/cards.json` (0600). Each entry holds the app id, the card
exactly as approved, `show` or `hide`, the package SHA-256 and the time. At most 128 entries are kept, newest
last. A changed label, caption or accent is a different card and needs a new decision. The record never leaves
the computer except as the approved cards baked into the launcher package.

## Launcher behaviour

1. **Validation.** Cards baked into the package are validated again by the launcher (`launcher/js/cards.js`).
   At most 8 are shown.
2. **Placement.** A card stands in for its app's tile:
   - only while the app is installed (in the TV's app list);
   - only when `module_cards` is on;
   - never for an app in `hidden_apps`.

   With `dock_only` on, an app with an approved card is on Home.
3. **Isolation.** The first failure of any kind in the card feature switches cards off for the rest of the
   page's life, with one notice. Home goes on as with `module_cards` false (as upstream's `CardFeature`).
