import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from foxverify import conf
from foxverify.tests import fixture, project_header, read_fixture

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
    """Every project's 9999demo.h and 9999skel.h parse to the expected blocks."""

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

    def test_classic_demo_values(self):
        block = conf.select(project_header(CLASSIC), conf.defined_for("classic_discoverable", "HARD"))
        self.assertEqual(block.string("NAME"), "Demo Case BTC Hard Fox")
        self.assertEqual(block.mac("MAC_ADDR"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(block.integer("TIME_TO_WAKE"), 30)
        self.assertEqual(block.integer("TIME_TO_SLEEP"), 30)
        self.assertEqual(block.display("NAME"), "Demo Case BTC Hard Fox")
        self.assertEqual(block.display("MAC_ADDR"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(block.display("TIME_TO_WAKE"), "30")

    def test_ibeacon_demo_values(self):
        block = conf.select(project_header(IBEACON), conf.defined_for("iBeacon", "MEDIUM"))
        self.assertEqual(block.string("DEVICE_NAME"), "Demo Cath BLE Medium Fox")
        self.assertEqual(block.string("BEACON_UUID"), "162EEB7B-743C-47E9-9414-BBD6149B4E40")
        self.assertEqual(block.integer("MAJOR"), 5)
        self.assertEqual(block.integer("MINOR"), 88)
        self.assertEqual(block.integer("SIGNAL_POWER"), 0xC5)
        self.assertEqual(block.mac("MAC_ADDR"), "F2:63:89:10:8D:1D")

    def test_wifi_demo_values(self):
        text = project_header(WIFI)
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

    def test_zigbee_demo_values(self):
        block = conf.select(project_header(ZIGBEE), conf.defined_for("zigbee_coordinator", "EASY"))
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
