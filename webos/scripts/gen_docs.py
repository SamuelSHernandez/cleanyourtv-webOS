#!/usr/bin/env python3
"""Write the generated parts of the docs from the code, so they cannot drift.

    python3 webos/scripts/gen_docs.py           # rewrite
    python3 webos/scripts/gen_docs.py --check   # exit 1 if a file would change (tests/test_docs.py runs this)

Generated: the key table in themes/README.md (from the schema in launcher/js/config.js) and the theme table
(from the folders under themes/). Text between `<!-- generated:NAME -->` and `<!-- /generated:NAME -->` is
replaced; everything else in the file is left as written.
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cytv_webos import themes  # noqa: E402


def type_text(spec):
    t = spec["type"]
    if t == "int":
        return f"{spec['min']} to {spec['max']}"
    if t == "enum":
        return " or ".join(f"`{v}`" for v in spec["values"])
    return {"bool": "bool", "color": "`#RRGGBB`", "appIds": "list of app ids", "appLabels": 'list of `"id=Name"`',
            "appKeys": 'list of `"code:target"`', "appId": "app id", "text": f"text (up to {spec.get('max')})",
            "locale": "language tag", "moods": "object"}.get(t, t)


def default_text(spec):
    d = spec["default"]
    if d is None or d == "" or d == []:
        return "unset"
    return "`" + json.dumps(d) + "`"


def keys_table():
    rows = ["| Key | Type | Default | Meaning |", "|---|---|---|---|"]
    for key, spec in themes.schema().items():
        on_tv = " (also in Launcher settings on the TV)" if spec.get("onTv") else ""
        rows.append(f"| `{key}` | {type_text(spec)} | {default_text(spec)} | {spec['doc']}{on_tv} |")
    return "\n".join(rows)


DESCRIPTIONS = {
    "default": "The built-in look written out as JSON, as a starting point for your own",
    "dock-only": "Only the dock apps on Home, three big tiles; every other app waits in the App library (`dock_only`)",
    "six-columns": "Six smaller tiles per row and one grid row visible under the dock",
    "night": "A dark time-of-day sky, a rim-only focus, calm motion and the clock screensaver after ten minutes",
    "aurora": "Teal and violet curtains of light drawn in code (`make_wallpaper.py`), a frosted dock and a halo focus",
}


def themes_table():
    rows = ["| Theme | What it does | Screenshot |", "|---|---|---|"]
    for folder in sorted(p for p in themes.THEMES.iterdir() if (p / "config.json").is_file()):
        desc = DESCRIPTIONS.get(folder.name, "")
        rows.append(f'| `{folder.name}/` | {desc} | <img src="{folder.name}/screenshot.jpg" width="320" alt="{folder.name} theme"> |')
    return "\n".join(rows)


def replace(text, name, body):
    pattern = re.compile(rf"(<!-- generated:{name} -->\n).*?(\n<!-- /generated:{name} -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"marker generated:{name} not found")
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), text)


def main():
    check = "--check" in sys.argv[1:]
    path = themes.THEMES / "README.md"
    old = path.read_text(encoding="utf-8")
    new = replace(replace(old, "keys", keys_table()), "themes", themes_table())
    if check:
        if new != old:
            print(f"{path} is out of date: run python3 webos/scripts/gen_docs.py")
            return 1
        return 0
    path.write_text(new, encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
