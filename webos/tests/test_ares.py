"""The ares-cli transport: argument arrays only, defensive parsing, and honest error classes."""
import subprocess
import unittest

import faketv  # noqa: F401  (puts webos/ on sys.path)

from cytv_webos.ares import AresTransport, PairingError
from cytv_webos.errors import LinkLost, Refused, TransportError


class Runner:
    def __init__(self, stdout="", stderr="", code=0, timeout=False):
        self.result = (stdout, stderr, code)
        self.timeout = timeout
        self.argv = []

    def __call__(self, argv, **kw):
        self.argv.append(argv)
        assert isinstance(argv, list) and not kw.get("shell"), "never a shell string"
        if self.timeout:
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
        out, err, code = self.result
        return subprocess.CompletedProcess(argv, code, out, err)


def transport(runner, have=True):
    return AresTransport("tv", runner=runner, which=lambda t: "/usr/bin/" + t if have else None)


class AresTest(unittest.TestCase):
    def test_listfull_parsing(self):
        out = ("\x1b[32mid : io.github.samuelshernandez.cytvwebos\x1b[0m\nversion : 0.1.0\ntype : web\n\n"
               "id : netflix\nversion : 5.2.1\n")
        self.assertEqual(transport(Runner(out)).installed(),
                         {"io.github.samuelshernandez.cytvwebos": "0.1.0", "netflix": "5.2.1"})
        self.assertEqual(transport(Runner("")).installed(), {})

    def test_empty_list_as_cli_3_2_6_prints_it(self):
        # Observed on a 50UQ7570PUJ (webOS 22, firmware 04.60.91) with no Developer Mode apps, 2026-10-26.
        self.assertEqual(transport(Runner("[Info] Set target device : tv\n")).installed(), {})
        info = transport(Runner("[Info] Set target device : tv\nmodelName : 50UQ7570PUJ\nsdkVersion : 7.6.0\n")).device_info()
        self.assertEqual(info, {"modelName": "50UQ7570PUJ", "sdkVersion": "7.6.0"})

    def test_unreadable_list_is_an_error_not_an_empty_tv(self):
        with self.assertRaises(TransportError):
            transport(Runner("something new and different\n")).installed()

    def test_system_info_keeps_only_well_formed_keys(self):
        info = transport(Runner("modelName : OLED55C3\nsdkVersion : 8.2.0\nweird key! : x\n")).device_info()
        self.assertEqual(info, {"modelName": "OLED55C3", "sdkVersion": "8.2.0"})
        with self.assertRaises(TransportError):
            transport(Runner("\n")).device_info()

    def test_key_refused_is_a_pairing_error(self):
        r = Runner(stderr="ERROR: All configured authentication methods failed", code=1)
        with self.assertRaises(PairingError):
            transport(r).install("x.ipk")

    def test_network_loss_during_a_mutation_is_link_lost(self):
        with self.assertRaises(LinkLost):
            transport(Runner(stderr="Error: connect ECONNRESET", code=1)).install("x.ipk")
        with self.assertRaises(LinkLost):
            transport(Runner(timeout=True)).remove("netflix")

    def test_network_loss_on_a_read_is_not_an_unknown_outcome(self):
        with self.assertRaises(TransportError) as ctx:
            transport(Runner(stderr="Error: connect ETIMEDOUT", code=1)).installed()
        self.assertNotIsInstance(ctx.exception, LinkLost)

    def test_missing_cli(self):
        r = Runner()
        with self.assertRaises(Refused):
            transport(r, have=False).install("x.ipk")
        self.assertEqual(r.argv, [])

    def test_ids_and_device_names_are_validated_before_running(self):
        r = Runner()
        for bad in ("--remove", "-x", "a b", "a;b", ""):
            with self.assertRaises(Refused):
                transport(r).launch(bad)
        self.assertEqual(r.argv, [])
        with self.assertRaises(Refused):
            AresTransport("tv; rm -rf /")

    def test_arguments_are_passed_as_an_array(self):
        r = Runner()
        transport(r).remove("youtube.leanback.v4")
        self.assertEqual(r.argv[0], ["ares-install", "--device", "tv", "--remove", "youtube.leanback.v4"])


if __name__ == "__main__":
    unittest.main()
