"""Errors the CLI turns into one readable line instead of a traceback."""
import re


class Refused(Exception):
    """A check refused the operation before anything reached the TV."""


class TransportError(Exception):
    """The TV, or the tool that talks to it, did not give a usable answer."""


class LinkLost(TransportError):
    """The connection dropped. After a mutation this means the outcome is unknown."""


_IPV4 = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d{1,5})?\b")
_IPV6 = re.compile(r"\[?\b[0-9A-Fa-f]{0,4}(:[0-9A-Fa-f]{0,4}){2,7}\b\]?(:\d{1,5})?")
_MAC = re.compile(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def scrub(text):
    """Text from the TV or its tools, with addresses taken out before it reaches a report or record."""
    text = _MAC.sub("<mac>", str(text))
    text = _IPV4.sub("<tv address>", text)
    return _IPV6.sub(lambda m: "<tv address>" if m.group(0).count(":") >= 2 else m.group(0), text)
