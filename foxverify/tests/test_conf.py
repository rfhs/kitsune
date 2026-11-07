import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from foxverify import conf
from foxverify.tests import fixture, frozen_text, project_header, read_fixture

CLASSIC = "bluetooth/classic_discoverable"
IBEACON = "bluetooth/iBeacon"
WIFI = "wifi/wifi_ap_client"
ZIGBEE = "zigbee/zigbee_coordinator"

CLASSIC_NAMES = ["NAME", "MAC_ADDR", "TIME_TO_WAKE", "TIME_TO_SLEEP"]
IBEACON_NAMES = ["DEVICE_NAME", "BEACON_UUID", "MAJOR", "MINOR", "SIGNAL_POWER", "MAC_ADDR"]
WIFI_AP_NAMES = ["FSSID", "PSK", "MAC_ADDR", "CHANNEL", "SSID_HIDDEN", "MAX_CLIENTS",
                 "TIME_TO_WAKE", "TIME_TO_SLEEP", "TXPOWER"]
WIFI_CLIENT_NAMES = ["FSSID", "PSK", "MAC_ADDR", "TIME_TO_WAKE", "TIME_TO_SLEEP", "TXPOWER"]
ZIGBEE_NAMES = ["MAC_ADDR", "EXT_PAN_ID", "CHANNEL", "PAN_ID", "TIME_TO_WAKE", "TIME_TO_SLEEP",
                "PACKET_INTERVAL", "TXPOWER"]


class StripCommentsTest(unittest.TestCase):
    def test_line_and_block_comments_go_strings_stay(self):
        text = 'a // one\nb /* two */ c\n"x // y" /* multi\nline */ d\n'
        self.assertEqual(conf.strip_comments(text), 'a  \nb   c\n"x // y"  \n d\n')

    def test_unterminated_block_comment_is_an_error(self):
        with self.assertRaises(conf.ConfError):
            conf.strip_comments("/* never closed")


class EvaluateTest(unittest.TestCase):
    def test_defined_forms(self):
        defined = frozenset(["A", "B"])
        self.assertTrue(conf._evaluate("defined(A)", defined))
        self.assertTrue(conf._evaluate("defined A", defined))
        self.assertFalse(conf._evaluate("defined(C)", defined))
        self.assertTrue(conf._evaluate("!defined(C)", defined))
        self.assertTrue(conf._evaluate("defined(A) && defined(B)", defined))
        self.assertFalse(conf._evaluate("defined(A) && defined(C)", defined))
        self.assertTrue(conf._evaluate("defined(C) || defined(B)", defined))
        self.assertTrue(conf._evaluate("(defined(C) || defined(B)) && !defined(C)", defined))

    def test_unsupported_expression_is_an_error(self):
        with self.assertRaises(conf.ConfError):
            conf._evaluate("CHANNEL > 0", frozenset())
        with self.assertRaises(conf.ConfError):
            conf._evaluate("(defined(A)", frozenset())


class DemoHeaderTest(unittest.TestCase):
    """Every project's 9999demo.h and 9999skel.h parse to the expected blocks,
    and the frozen copies under fixtures/headers/ parse to their known values.
    The live demo is rolled anew each year, so only its structure is checked
    here; LiveDemoRangeTest checks its values against the guards' ranges."""

    def check_blocks(self, text, expected_keys, names):
        found = conf.blocks(text)
        self.assertEqual(sorted(k for k in found if k), sorted(expected_keys))
        for key in expected_keys:
            self.assertEqual(list(found[key]), names, key)

    def test_classic_blocks(self):
        for name in ("9999demo.h", "9999skel.h"):
            self.check_blocks(project_header(CLASSIC, name), ["EASY", "HARD"], CLASSIC_NAMES)

    def test_ibeacon_blocks(self):
        for name in ("9999demo.h", "9999skel.h"):
            self.check_blocks(project_header(IBEACON, name), ["EASY", "MEDIUM", "HARD"],
                              IBEACON_NAMES)

    def test_wifi_blocks(self):
        for name in ("9999demo.h", "9999skel.h"):
            found = conf.blocks(project_header(WIFI, name))
            self.assertEqual(sorted(k for k in found if k),
                             sorted(["AP EASY", "AP HARD", "AP FIVEEASY", "AP FIVEHARD",
                                     "CLIENT EASY", "CLIENT HARD"]))
            for key in ("AP EASY", "AP HARD", "AP FIVEEASY", "AP FIVEHARD"):
                self.assertEqual(list(found[key]), WIFI_AP_NAMES, key)
            for key in ("CLIENT EASY", "CLIENT HARD"):
                self.assertEqual(list(found[key]), WIFI_CLIENT_NAMES, key)

    def test_zigbee_blocks(self):
        for name in ("9999demo.h", "9999skel.h"):
            self.check_blocks(project_header(ZIGBEE, name),
                              ["COORDINATOR EASY", "COORDINATOR HARD"], ZIGBEE_NAMES)

    def test_wifi_power_table_in_comments_is_not_a_define(self):
        found = conf.blocks(project_header(WIFI))
        self.assertNotIn("", found)
        for values in found.values():
            self.assertFalse(any(name.startswith("WIFI_POWER") for name in values))

    def test_classic_frozen_values(self):
        block = conf.select(frozen_text("classic_discoverable"), conf.defined_for("classic_discoverable", "HARD"))
        self.assertEqual(block.string("NAME"), "Demo Case BTC Hard Fox")
        self.assertEqual(block.mac("MAC_ADDR"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(block.integer("TIME_TO_WAKE"), 30)
        self.assertEqual(block.integer("TIME_TO_SLEEP"), 30)
        self.assertEqual(block.display("NAME"), "Demo Case BTC Hard Fox")
        self.assertEqual(block.display("MAC_ADDR"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(block.display("TIME_TO_WAKE"), "30")

    def test_ibeacon_frozen_values(self):
        block = conf.select(frozen_text("iBeacon"), conf.defined_for("iBeacon", "MEDIUM"))
        self.assertEqual(block.string("DEVICE_NAME"), "Demo Cath BLE Medium Fox")
        self.assertEqual(block.string("BEACON_UUID"), "162EEB7B-743C-47E9-9414-BBD6149B4E40")
        self.assertEqual(block.integer("MAJOR"), 5)
        self.assertEqual(block.integer("MINOR"), 88)
        self.assertEqual(block.integer("SIGNAL_POWER"), 0xC5)
        self.assertEqual(block.mac("MAC_ADDR"), "F2:63:89:10:8D:1D")

    def test_wifi_frozen_values(self):
        text = frozen_text("wifi_ap_client")
        ap = conf.select(text, conf.defined_for("wifi_ap_client", "HARD", "AP"))
        self.assertEqual(ap.string("FSSID"), "Demo YT WiFi AP Hard Fox")
        self.assertEqual(ap.string("PSK"), "0123456789")
        self.assertEqual(ap.mac("MAC_ADDR"), "F2:72:C1:79:16:1B")
        self.assertEqual(ap.integer("CHANNEL"), 0)
        self.assertEqual(ap.integer("SSID_HIDDEN"), 0)
        self.assertEqual(ap.integer("MAX_CLIENTS"), 1)
        self.assertEqual(ap.identifier("TXPOWER"), "WIFI_POWER_7dBm")
        self.assertEqual(ap.display("TXPOWER"), "WIFI_POWER_7dBm")
        five = conf.select(text, conf.defined_for("wifi_ap_client", "FIVEEASY", "AP"))
        self.assertEqual(five.integer("CHANNEL"), 36)
        client = conf.select(text, conf.defined_for("wifi_ap_client", "EASY", "CLIENT"))
        self.assertEqual(client.string("FSSID"), "Demo Ng WiFi Client Easy Fox")
        self.assertNotIn("CHANNEL", client)
        self.assertEqual(len(client), len(WIFI_CLIENT_NAMES))

    def test_zigbee_frozen_values(self):
        block = conf.select(frozen_text("zigbee_coordinator"), conf.defined_for("zigbee_coordinator", "EASY"))
        self.assertEqual(block.mac("MAC_ADDR"), "F2:5A:3C:91:0E:7B:44:D8")
        self.assertEqual(block.raw("EXT_PAN_ID"), "MAC_ADDR")
        self.assertEqual(block.mac("EXT_PAN_ID"), "F2:5A:3C:91:0E:7B:44:D8")
        self.assertEqual(block.display("EXT_PAN_ID"), "F2:5A:3C:91:0E:7B:44:D8")
        self.assertEqual(block.integer("CHANNEL"), 15)
        self.assertEqual(block.integer("PAN_ID"), 0x1337)
        self.assertEqual(conf.format_u16(block.integer("PAN_ID")), "0x1337")
        self.assertFalse(block.is_bare_zero("PAN_ID"))
        self.assertEqual(block.integer("PACKET_INTERVAL"), 1)
        self.assertEqual(block.integer("TXPOWER"), 20)

    def test_zigbee_without_coordinator_macro_selects_nothing(self):
        block = conf.select(project_header(ZIGBEE), ["EASY"])
        self.assertEqual(len(block), 0)

    def test_difficulty_with_no_block_selects_nothing(self):
        block = conf.select(project_header(CLASSIC), conf.defined_for("classic_discoverable", "MEDIUM"))
        self.assertNotIn("MAC_ADDR", block)


class LiveDemoRangeTest(unittest.TestCase):
    """Every value in every block of the live 9999demo.h is one the shared
    headers' compile time guards accept, whatever make_conference rolled.
    Nothing here names a demo value."""

    def unicast_mac(self, block, name, length, label):
        data = conf.parse_byte_array(block.raw(name), name)
        self.assertEqual(len(data), length, label)
        self.assertEqual(data[0] & 0x01, 0, label)
        self.assertTrue(any(data), label)

    def test_classic(self):
        for key in ("EASY", "HARD"):
            block = conf.select(project_header(CLASSIC), conf.defined_for("classic_discoverable", key))
            self.assertTrue(1 <= len(block.string("NAME")) <= 32, key)
            self.unicast_mac(block, "MAC_ADDR", 6, key)
            self.assertGreaterEqual(block.integer("TIME_TO_WAKE"), 15, key)
            self.assertGreaterEqual(block.integer("TIME_TO_SLEEP"), 0, key)

    def test_ibeacon(self):
        for key in ("EASY", "MEDIUM", "HARD"):
            block = conf.select(project_header(IBEACON), conf.defined_for("iBeacon", key))
            self.assertTrue(1 <= len(block.string("DEVICE_NAME")) <= 29, key)
            self.assertRegex(block.string("BEACON_UUID"), r"^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
            self.assertTrue(0 <= block.integer("MAJOR") <= 65535, key)
            self.assertTrue(0 <= block.integer("MINOR") <= 65535, key)
            self.assertTrue(-128 <= block.integer("SIGNAL_POWER") <= 255, key)
            self.unicast_mac(block, "MAC_ADDR", 6, key)

    def test_wifi(self):
        text = project_header(WIFI)
        for mode in ("AP", "CLIENT"):
            for difficulty in ("EASY", "HARD", "FIVEEASY", "FIVEHARD"):
                block = conf.select(text, conf.defined_for("wifi_ap_client", difficulty, mode))
                if not block:
                    continue
                label = mode + " " + difficulty
                self.assertTrue(1 <= len(block.string("FSSID")) <= 32, label)
                self.assertRegex(block.string("PSK"), r"^[ -~]{8,63}$", label)
                self.unicast_mac(block, "MAC_ADDR", 6, label)
                self.assertRegex(block.identifier("TXPOWER"), r"^WIFI_POWER_", label)
                self.assertGreaterEqual(block.integer("TIME_TO_WAKE"), 1, label)
                if mode == "AP":
                    allowed = [0, 36, 40, 44, 48, 149, 153, 157, 161, 165] if difficulty.startswith("FIVE") else range(12)
                    self.assertIn(block.integer("CHANNEL"), allowed, label)
                    self.assertIn(block.integer("SSID_HIDDEN"), (0, 1), label)
                    self.assertTrue(1 <= block.integer("MAX_CLIENTS") <= 10, label)

    def test_zigbee(self):
        for key in ("EASY", "HARD"):
            block = conf.select(project_header(ZIGBEE), conf.defined_for("zigbee_coordinator", key))
            self.unicast_mac(block, "MAC_ADDR", 8, key)
            ext = conf.parse_byte_array(block.resolved("EXT_PAN_ID"), "EXT_PAN_ID")
            self.assertEqual(len(ext), 8, key)
            self.assertNotIn(ext, (bytes(8), bytes([0xFF] * 8)), key)
            self.assertIn(block.integer("CHANNEL"), [0] + list(range(11, 27)), key)
            self.assertTrue(0 <= block.integer("PAN_ID") <= 0xFFFE, key)
            self.assertTrue(-15 <= block.integer("TXPOWER") <= 20, key)
            self.assertTrue(1 <= block.integer("PACKET_INTERVAL") <= 255, key)
            self.assertLess(block.integer("PACKET_INTERVAL"), block.integer("TIME_TO_WAKE"), key)


class CommentHeaderTest(unittest.TestCase):
    def test_defines_in_comments_are_ignored(self):
        text = read_fixture("headers", "comments.h")
        found = conf.blocks(text)
        self.assertEqual(sorted(found), ["EASY", "HARD"])
        for values in found.values():
            self.assertFalse(any(name.startswith("TRAP") for name in values), values)
            self.assertNotIn("RFHS_CHALLENGE_NAME", values)
            self.assertNotIn("FOX_KEYWORDS", values)
            self.assertNotIn("WIFI_POWER_19_5dBm", values)
        easy = conf.select(text, ["EASY"])
        self.assertEqual(easy.string("NAME"), "Slashes // inside a string stay")
        self.assertEqual(easy.mac("MAC_ADDR"), "F2:81:5A:C1:A3:26")
        self.assertEqual(easy.integer("TIME_TO_WAKE"), 300)
        self.assertEqual(easy.names(), CLASSIC_NAMES)


class PanZeroTest(unittest.TestCase):
    def test_bare_zero_is_random_and_0x0000_is_pan_zero(self):
        text = read_fixture("headers", "pan_zero.h")
        easy = conf.select(text, conf.defined_for("zigbee_coordinator", "EASY"))
        hard = conf.select(text, conf.defined_for("zigbee_coordinator", "HARD"))
        self.assertTrue(easy.is_bare_zero("PAN_ID"))
        self.assertEqual(easy.integer("PAN_ID"), 0)
        self.assertEqual(easy.integer("CHANNEL"), 0)
        self.assertFalse(hard.is_bare_zero("PAN_ID"))
        self.assertEqual(hard.integer("PAN_ID"), 0)
        self.assertEqual(hard.raw("PAN_ID"), "0x0000")
        self.assertEqual(conf.format_u16(hard.integer("PAN_ID")), "0x0000")
        self.assertEqual(hard.integer("CHANNEL"), 11)
        self.assertEqual(hard.integer("TXPOWER"), -15)
        self.assertEqual(hard.mac("EXT_PAN_ID"), "11:22:33:44:55:66:77:88")


class ValueParsingTest(unittest.TestCase):
    def test_c_strings(self):
        self.assertEqual(conf.parse_c_string('"plain"'), "plain")
        self.assertEqual(conf.parse_c_string(r'"q\"uote\\ tab\t nl\n"'), 'q"uote\\ tab\t nl\n')
        self.assertEqual(conf.parse_c_string(r'"\x41\102"'), "AB")
        self.assertEqual(conf.parse_c_string('"two" "parts"'), "twoparts")
        with self.assertRaises(conf.ConfError):
            conf.parse_c_string('"open')
        with self.assertRaises(conf.ConfError):
            conf.parse_c_string("bare")

    def test_c_integers(self):
        self.assertEqual(conf.parse_c_int("15"), 15)
        self.assertEqual(conf.parse_c_int("0x1337"), 0x1337)
        self.assertEqual(conf.parse_c_int("0XDEAD"), 0xDEAD)
        self.assertEqual(conf.parse_c_int("0xc5"), 197)
        self.assertEqual(conf.parse_c_int("0"), 0)
        self.assertEqual(conf.parse_c_int("0x0000"), 0)
        self.assertEqual(conf.parse_c_int("-4"), -4)
        self.assertEqual(conf.parse_c_int("017"), 15)
        self.assertEqual(conf.parse_c_int("10u"), 10)
        self.assertEqual(conf.parse_c_int("(5)"), 5)
        with self.assertRaises(conf.ConfError):
            conf.parse_c_int("WIFI_POWER_17dBm")
        with self.assertRaises(conf.ConfError):
            conf.parse_c_int('"5"')

    def test_byte_arrays(self):
        self.assertEqual(conf.parse_byte_array("{0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x26}"),
                         bytes([0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x26]))
        self.assertEqual(conf.parse_byte_array("{ 0x00, 0x0b , 0x0c,}"), bytes([0, 11, 12]))
        self.assertEqual(conf.format_bytes(conf.parse_byte_array("{0x00, 0x0b}")), "00:0B")
        with self.assertRaises(conf.ConfError):
            conf.parse_byte_array("{0x100}")
        with self.assertRaises(conf.ConfError):
            conf.parse_byte_array("0xF2")

    def test_block_errors(self):
        block = conf.Block({"A": '"text"', "B": "5", "C": "{0x01}", "D": "NAME", "E": "E"})
        with self.assertRaises(conf.ConfError):
            block.raw("MISSING")
        with self.assertRaises(conf.ConfError):
            block.integer("A")
        with self.assertRaises(conf.ConfError):
            block.string("B")
        with self.assertRaises(conf.ConfError):
            block.identifier("C")
        self.assertEqual(block.identifier("D"), "NAME")
        self.assertEqual(block.resolved("E"), "E")

    def test_undef_removes_a_value(self):
        block = conf.select("#define A 1\n#undef A\n#define B 2\n", [])
        self.assertEqual(block.as_dict(), {"B": "2"})

    def test_else_and_elif_select_one_branch(self):
        text = "#if defined(A)\n#define X 1\n#elif defined(B)\n#define X 2\n#else\n#define X 3\n#endif\n"
        self.assertEqual(conf.select(text, ["A"]).integer("X"), 1)
        self.assertEqual(conf.select(text, ["A", "B"]).integer("X"), 1)
        self.assertEqual(conf.select(text, ["B"]).integer("X"), 2)
        self.assertEqual(conf.select(text, []).integer("X"), 3)
        self.assertEqual(sorted(conf.blocks(text)), sorted(["A", "B", "!(defined(A) || defined(B))"]))

    def test_malformed_conditionals_are_errors(self):
        for text in ("#endif\n", "#if defined(A)\n", "#else\n", "#if defined(A)\n#else\n#elif defined(B)\n#endif\n"):
            with self.assertRaises(conf.ConfError):
                conf.blocks(text)


class MainTest(unittest.TestCase):
    def test_dump_all_blocks(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = conf.main([fixture("headers", "pan_zero.h")])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(sorted(data), ["COORDINATOR EASY", "COORDINATOR HARD"])
        self.assertEqual(data["COORDINATOR HARD"]["PAN_ID"], "0x0000")

    def test_dump_selected_block(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = conf.main([fixture("headers", "pan_zero.h"), "COORDINATOR", "EASY"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["PAN_ID"], "0")
        self.assertEqual(list(data), ZIGBEE_NAMES)

    def test_usage_without_arguments(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(conf.main([]), 2)
        self.assertIn("usage", err.getvalue())


if __name__ == "__main__":
    unittest.main()
