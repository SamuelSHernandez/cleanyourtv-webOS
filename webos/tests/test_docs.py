"""The docs stay connected to the code: cited tests exist, links resolve, commands are real."""
from pathlib import Path
import re
import unittest

import faketv  # noqa: F401

from cytv_webos import cli

ROOT = Path(__file__).resolve().parents[1]
DOCS = sorted([ROOT / n for n in ("README.md", "THIRD_PARTY.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md")]
              + list((ROOT / "docs").rglob("*.md")) + list((ROOT / "themes").glob("*.md"))
              + list((ROOT / "addons").rglob("*.md")))
TEST_SOURCES = "\n".join(p.read_text() for p in (ROOT / "tests").rglob("*.py")) + "\n".join(
    p.read_text() for p in (ROOT / "tests" / "js").glob("*.js"))


class DocsTest(unittest.TestCase):
    def test_cited_tests_exist(self):
        for doc in DOCS:
            for name in re.findall(r"`(?:test_\w+\.)?(test_\w+|[A-Z]\w+Test)(?:\.test_\w+)?`", doc.read_text()):
                self.assertRegex(TEST_SOURCES, rf"(def|class) {name}\b", f"{doc.name} cites {name}")
            for js in re.findall(r"`logic\.test\.js` \"([^\"]+?)…\"", doc.read_text()):
                self.assertIn(js, TEST_SOURCES)

    def test_relative_links_resolve(self):
        for doc in DOCS:
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text()):
                if re.match(r"[a-z]+:", target):
                    continue
                self.assertTrue((doc.parent / target).exists(), f"{doc.name} links to missing {target}")

    def test_commands_in_docs_exist(self):
        commands = set(cli.parser()._subparsers._group_actions[0].choices)
        home = {"status", "enable", "watch", "stop", "resume", "deactivate"}
        for doc in DOCS:
            for cmd, rest in re.findall(r"cytv-webos (\w[\w-]*)( \w+)?", doc.read_text()):
                self.assertIn(cmd, commands, f"{doc.name}: cytv-webos {cmd}")
                if cmd == "home" and rest.strip() and rest.strip() not in ("to",):
                    self.assertIn(rest.strip(), home, f"{doc.name}: cytv-webos home{rest}")

    def test_no_private_identifiers_in_docs(self):
        for doc in DOCS:
            text = doc.read_text()
            for ip in re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text):
                self.assertIn(ip, ("192.168.1.50", "127.0.0.1"), f"{doc.name}: use 192.168.1.50 as the example address")
            self.assertNotRegex(text, r"(?i)\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b", f"{doc.name}: MAC address")


if __name__ == "__main__":
    unittest.main()
