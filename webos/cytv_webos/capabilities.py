"""Read-only capability detection and the compatibility report.

Nothing here changes the TV. Only facts needed for a decision are collected, and only the model,
SDK and firmware leave this module: no serial number, MAC address, device id, IP address or
account. Passing these checks makes a TV eligible for a path; it does not certify it.
"""
from .errors import Refused, TransportError, scrub
from . import integration, journal, profiles

FACT_KEYS = ("modelName", "sdkVersion", "firmwareVersion")


def collect(transport, profile_list, ssap_session=None, launcher_id=None, device=None):
    """A report dict. Every unanswered question is recorded as such, never guessed."""
    report = {"tools": {}, "tv": {}, "profile": None, "browser_floor": None, "apps": {},
              "conflicts": [], "shortcuts": {}, "native": "not applicable: this release ships no native code",
              "backends": {}, "selected_backend": None, "integration_state": None, "problems": []}
    missing = transport.missing_tools()
    report["tools"]["missing"] = missing
    if missing:
        report["problems"].append("LG's webOS CLI is missing: " + ", ".join(missing))
    else:
        try:
            report["tools"]["ares_version"] = transport.cli_version()
        except (TransportError, Refused) as e:
            report["problems"].append(f"ares CLI version unreadable: {e}")

    facts = {}
    if not missing:
        try:
            info = transport.device_info()
            facts = {k: info[k] for k in FACT_KEYS if k in info}
        except (TransportError, Refused) as e:
            report["problems"].append(f"TV system information unavailable: {e}")
    report["tv"] = facts

    profile = profiles.select(profile_list, facts.get("sdkVersion"))
    if facts.get("sdkVersion") and not profile:
        report["problems"].append(f"no profile covers SDK {facts['sdkVersion']}: unsupported")
    report["profile"] = profile["id"] if profile else None
    report["browser_floor"] = profile["browser_floor"] if profile else None

    apps, source = {}, None
    if ssap_session is not None:
        try:
            from . import ssap
            apps, source = ssap.all_apps(ssap_session), "ssap"
        except (TransportError, Refused) as e:
            report["problems"].append(f"SSAP app list unavailable: {e}")
    if not apps and not missing:
        try:
            apps, source = transport.installed(), "developer-mode-only"
        except (TransportError, Refused) as e:
            report["problems"].append(f"installed app list unavailable: {e}")
    report["apps"] = {"count": len(apps), "source": source,
                      "launcher_installed": bool(launcher_id and launcher_id in apps),
                      "launcher_version": apps.get(launcher_id) if launcher_id else None}
    if source == "developer-mode-only":
        report["problems"].append("only Developer Mode apps were visible (pair SSAP for the full list); conflict "
                                  "detection is incomplete")

    if profile:
        for c in profile["known_conflicts"]:
            if c["id"] in apps:
                report["conflicts"].append({"id": c["id"], "kind": c["kind"], "what": c["what"]})
        for kind, candidates in profile["shortcut_candidates"].items():
            found = next((a for a in candidates if a in apps), None) if source == "ssap" else None
            report["shortcuts"][kind] = found

    state = None
    if device:
        try:
            state = integration.load(device)
        except Refused as e:
            report["problems"].append(str(e))
    report["selected_backend"] = state["backend"] if state else None
    report["integration_state"] = state["state"] if state else None

    ready = False
    if device:
        try:
            j = journal.load(device)
            ready = journal.launcher_ready(j)
        except Refused as e:
            report["problems"].append(str(e))
    reachable = bool(facts)
    blocking = [c for c in report["conflicts"] if c["kind"] in ("home-controller", "root")]
    if profile:
        for name, spec in profile["backends"].items():
            reasons = []
            if not reachable:
                reasons.append("TV not reachable through the webOS CLI")
            if "ssap-paired" in spec["requires"] and ssap_session is None:
                reasons.append("SSAP not paired")
            if "launcher-ready" in spec["requires"] and not ready:
                reasons.append("launcher readiness not confirmed on the TV")
            if name != "manual" and blocking:
                reasons.append("another Home controller or root setup is present: "
                               + ", ".join(c["id"] for c in blocking))
            report["backends"][name] = {"eligible": not reasons, "reasons": reasons, "evidence": spec["evidence"]}
    report["problems"] = [scrub(p) for p in report["problems"]]
    return report


def render(report):
    lines = ["CleanYourTV webOS compatibility report (read-only; eligibility, not certification)", ""]
    tv = report["tv"]
    lines.append(f"TV:           {tv.get('modelName', '?')}, SDK {tv.get('sdkVersion', '?')}, "
                 f"firmware {tv.get('firmwareVersion', '?')}")
    lines.append(f"Profile:      {report['profile'] or 'none (unsupported or unknown)'}")
    lines.append(f"Browser:      {report['browser_floor'] or '?'}")
    lines.append(f"webOS CLI:    {report['tools'].get('ares_version') or ('missing' if report['tools'].get('missing') else '?')}")
    a = report["apps"]
    lines.append(f"Apps:         {a.get('count', 0)} seen via {a.get('source') or 'nothing'}; launcher "
                 f"{'installed ' + str(a.get('launcher_version') or '') if a.get('launcher_installed') else 'not installed'}")
    lines.append(f"Native code:  {report['native']}")
    for kind, app in report["shortcuts"].items():
        lines.append(f"Shortcut {kind:<8} {app or 'not found (hidden in the launcher)'}")
    for c in report["conflicts"]:
        lines.append(f"Conflict:     {c['id']} - {c['what']}")
    lines.append(f"Home backend: {report['selected_backend'] or '?'} ({report['integration_state'] or '?'})")
    for name, b in report["backends"].items():
        verdict = "eligible" if b["eligible"] else "not eligible: " + "; ".join(b["reasons"])
        lines.append(f"  {name:<17} {verdict} [evidence: {b['evidence']}]")
    for p in report["problems"]:
        lines.append(f"Problem:      {p}")
    return "\n".join(lines)
