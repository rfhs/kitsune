import os
import tempfile
import unittest

from foxverify import privileges
from foxverify.report import RunError

NET_BITS = (1 << 12) | (1 << 13)


class ToolTest(unittest.TestCase):
    def test_missing_tool_names_the_package(self):
        with self.assertRaises(RunError) as caught:
            privileges.require_tool("tshark", which=lambda name: None)
        self.assertIn("tshark is not installed", str(caught.exception))
        self.assertIn("wireshark-cli", str(caught.exception))

    def test_present_tool_returns_its_path(self):
        self.assertEqual(privileges.require_tool("iw", which=lambda name: "/usr/sbin/" + name), "/usr/sbin/iw")

    def test_require_tools_lists_every_missing_one(self):
        with self.assertRaises(RunError) as caught:
            privileges.require_tools(["ip", "iw", "tshark"], which=lambda name: "/bin/ip" if name == "ip" else None)
        self.assertIn("iw is not installed", str(caught.exception))
        self.assertIn("tshark is not installed", str(caught.exception))
        self.assertNotIn("ip is not", str(caught.exception))


class CapabilityTest(unittest.TestCase):
    def test_cap_eff_is_read_from_status(self):
        with tempfile.NamedTemporaryFile("w", suffix="-status", delete=False) as handle:
            handle.write("Name:\tpython3\nCapInh:\t0000000000000000\nCapEff:\t0000000000003000\n")
        self.addCleanup(os.unlink, handle.name)
        self.assertEqual(privileges.effective_capabilities(handle.name), 0x3000)
        self.assertEqual(privileges.effective_capabilities("/nonexistent"), 0)

    def test_root_or_capabilities(self):
        self.assertTrue(privileges.has_net_admin(lambda: 0, lambda: 0))
        self.assertTrue(privileges.has_net_admin(lambda: 1000, lambda: NET_BITS))
        self.assertFalse(privileges.has_net_admin(lambda: 1000, lambda: 1 << 12))
        self.assertFalse(privileges.has_net_admin(lambda: 1000, lambda: 0))

    def test_require_net_admin_message(self):
        with self.assertRaises(RunError) as caught:
            privileges.require_net_admin("btmgmt", lambda: 1000, lambda: 0)
        self.assertEqual(str(caught.exception),
                         "btmgmt needs root or the CAP_NET_ADMIN and CAP_NET_RAW capabilities; run this script with sudo")
        privileges.require_net_admin("btmgmt", lambda: 0, lambda: 0)

    def test_capture_through_a_capable_dumpcap(self):
        def getxattr(path, name):
            if path.endswith("/dumpcap"):
                return b"\x01\x00\x00\x02"
            raise OSError("no attribute")

        def no_xattr(path, name):
            raise OSError("no attribute")

        self.assertTrue(privileges.can_capture("/usr/bin/tshark", lambda: 1000, lambda: 0, getxattr, lambda p, m: True))
        self.assertFalse(privileges.can_capture("/usr/bin/tshark", lambda: 1000, lambda: 0, getxattr, lambda p, m: False))
        self.assertFalse(privileges.can_capture("/usr/bin/tshark", lambda: 1000, lambda: 0, no_xattr, lambda p, m: True))
        self.assertTrue(privileges.can_capture("/usr/bin/tshark", lambda: 0, lambda: 0, no_xattr, lambda p, m: False))
        with self.assertRaises(RunError):
            privileges.require_capture("/usr/bin/tshark", euid=lambda: 1000, capabilities=lambda: 0,
                                       getxattr=no_xattr, access=lambda p, m: True)


if __name__ == "__main__":
    unittest.main()
