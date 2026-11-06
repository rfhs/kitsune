import io
import os
import shutil
import tempfile
import unittest

from foxverify import conf, report, tshark, wifi
from foxverify.report import Deadline, RunError
from foxverify.serial_fox import parse_transcript
from foxverify.tests import frozen_text, read_fixture
from foxverify.tests.fakes import FakeReader, Recorder, deadline

HEADER = frozen_text("wifi_ap_client")
BEACONS = read_fixture("tshark", "ap_beacons.tsv").splitlines()
PROBES = read_fixture("tshark", "client_probes.tsv").splitlines()


def beacon(index):
    return wifi.parse_beacon(tshark.parse_line(BEACONS[index], wifi.AP_FIELDS))


class BeaconTest(unittest.TestCase):
    def test_visible_ap_beacon(self):
        b = beacon(0)
        self.assertEqual(b.bssid, "F2:F4:90:22:0D:0F")
        self.assertEqual(b.ssid, "Demo Hiro WiFi AP Easy Fox")
        self.assertFalse(b.hidden())
        self.assertEqual(b.claimed_channel(), 1)
        self.assertEqual(b.radio_channel(), 1)
        self.assertEqual(b.channel_text(), "1")
        self.assertEqual(b.security(), "WPA2-PSK/CCMP")
        self.assertAlmostEqual(b.time, 1730000000.123456)

    def test_hidden_ssid_is_zero_length(self):
        b = beacon(1)
        self.assertTrue(b.hidden())
        self.assertEqual(wifi.ssid_display(b.ssid, "whatever"), "(hidden)")
        self.assertTrue(wifi.ssid_hidden("000000"))
        self.assertTrue(wifi.ssid_hidden(""))
        self.assertFalse(wifi.ssid_hidden("Coffee"))

    def test_ssid_printed_as_hex_still_matches(self):
        b = beacon(2)
        self.assertTrue(wifi.ssid_matches(b.ssid, "Demo Hiro WiFi AP Easy Fox"))
        self.assertEqual(wifi.ssid_display(b.ssid, "Demo Hiro WiFi AP Easy Fox"), "Demo Hiro WiFi AP Easy Fox")
        self.assertFalse(wifi.ssid_matches(b.ssid, "Other"))
        self.assertFalse(wifi.ssid_matches("DEADBEEF", "Other"))
        self.assertTrue(wifi.ssid_matches("DEADBEEF", "DEADBEEF"))

    def test_open_network_has_no_rsn(self):
        b = beacon(3)
        self.assertEqual(b.security(), "open (no RSN element)")
        self.assertEqual(b.akms, [])

    def test_only_beacons_from_the_bssid_are_accepted(self):
        probe_response = tshark.parse_line(BEACONS[4], wifi.AP_FIELDS)
        self.assertFalse(wifi.is_beacon_from(probe_response, "F2:F4:90:22:0D:0F"))
        self.assertTrue(wifi.is_beacon_from(tshark.parse_line(BEACONS[0], wifi.AP_FIELDS), "f2:f4:90:22:0d:0f"))
        self.assertFalse(wifi.is_beacon_from(tshark.parse_line(BEACONS[3], wifi.AP_FIELDS), "f2:f4:90:22:0d:0f"))

    def test_five_ghz_channel_from_ht_operation_and_frequency(self):
        b = beacon(5)
        self.assertIsNone(b.ds_channel)
        self.assertEqual(b.claimed_channel(), 36)
        self.assertEqual(b.radio_channel(), 36)
        self.assertEqual(b.channel_text(), "36")

    def test_channel_disagreement_shows_both(self):
        b = beacon(6)
        self.assertEqual(b.channel_text(), "1 in beacon, received on 6")
        self.assertEqual(b.akms, [2, 8])
        self.assertEqual(b.security(), "WPA2-PSK/CCMP")

    def test_frequency_to_channel(self):
        self.assertEqual(wifi.frequency_to_channel(2412), 1)
        self.assertEqual(wifi.frequency_to_channel(2462), 11)
        self.assertEqual(wifi.frequency_to_channel(2484), 14)
        self.assertEqual(wifi.frequency_to_channel(5180), 36)
        self.assertEqual(wifi.frequency_to_channel(5825), 165)
        self.assertIsNone(wifi.frequency_to_channel(None))
        self.assertIsNone(wifi.frequency_to_channel(1234))

    def test_filters(self):
        self.assertEqual(wifi.beacon_filter("F2:F4:90:22:0D:0F"),
                         "wlan.fc.type_subtype == 0x0008 && wlan.bssid == f2:f4:90:22:0d:0f")
        self.assertEqual(wifi.probe_filter("F2:44:5E:10:97:F4"),
                         "wlan.fc.type_subtype == 0x0004 && wlan.sa == f2:44:5e:10:97:f4")

    def test_wait_for_beacon_skips_other_frames(self):
        dl, clock = deadline(60)
        reader = FakeReader(wifi.AP_FIELDS, [(0.5, BEACONS[3]), (0.5, BEACONS[4]), (0.5, BEACONS[0])], clock)
        b = wifi.wait_for_beacon(reader, "F2:F4:90:22:0D:0F", dl)
        self.assertEqual(b.ssid, "Demo Hiro WiFi AP Easy Fox")
        self.assertEqual(clock.now, 1001.5)

    def test_wait_for_beacon_gives_up_at_the_deadline(self):
        dl, clock = deadline(3)
        reader = FakeReader(wifi.AP_FIELDS, [(10.0, BEACONS[0])], clock)
        self.assertIsNone(wifi.wait_for_beacon(reader, "F2:F4:90:22:0D:0F", dl))


class ChannelChoiceTest(unittest.TestCase):
    def test_ap_channel_from_header_or_serial(self):
        easy = conf.select(HEADER, ["AP", "EASY"])
        hard = conf.select(HEADER, ["AP", "HARD"])
        readback = parse_transcript("Fox: wifi_ap_client EASY AP\nOperating channel: 7\n")
        self.assertEqual(wifi.ap_channel(easy, readback), 1)
        self.assertEqual(wifi.ap_channel(hard, readback), 7)
        self.assertIsNone(wifi.ap_channel(hard, parse_transcript("")))

    def test_probe_channels(self):
        client = conf.select(HEADER, ["CLIENT", "EASY"])
        self.assertEqual(wifi.probe_channels(client), list(range(1, 12)))
        self.assertEqual(wifi.probe_channels(conf.select(HEADER, ["AP", "EASY"])), [1])
        self.assertEqual(wifi.probe_channels(conf.select(HEADER, ["AP", "HARD"])), list(range(1, 12)))


class ProbeTest(unittest.TestCase):
    def test_collect_stops_at_the_probe_carrying_the_ssid(self):
        dl, clock = deadline(60)
        reader = FakeReader(wifi.CLIENT_FIELDS, [(0.2, line) for line in PROBES], clock)
        tuned = []
        probes = wifi.collect_probes(reader, "F2:44:5E:10:97:F4", "Demo Ng WiFi Client Easy Fox", dl,
                                     [6], tuned.append, clock=clock)
        self.assertEqual(tuned, [6])
        self.assertEqual(probes.mac, "F2:44:5E:10:97:F4")
        self.assertEqual(probes.count, 2)
        self.assertTrue(probes.carried("Demo Ng WiFi Client Easy Fox"))
        self.assertEqual(probes.channels, [1])
        self.assertEqual(probes.ssids, [None, "Demo Ng WiFi Client Easy Fox"])
        self.assertAlmostEqual(probes.first_time, 1730000001.0)

    def test_collect_hops_channels_while_waiting(self):
        dl, clock = deadline(10)
        reader = FakeReader(wifi.CLIENT_FIELDS, [(20.0, PROBES[3])], clock)
        tuned = []
        probes = wifi.collect_probes(reader, "F2:44:5E:10:97:F4", "x", dl, [1, 6, 11], tuned.append,
                                     dwell=3.0, clock=clock)
        self.assertFalse(probes.seen())
        self.assertEqual(tuned, [1, 6, 11, 1])
        self.assertTrue(dl.expired())

    def test_wildcard_probes_only(self):
        dl, clock = deadline(2)
        reader = FakeReader(wifi.CLIENT_FIELDS, [(0.1, PROBES[0]), (0.1, PROBES[1])], clock)
        probes = wifi.collect_probes(reader, "F2:44:5E:10:97:F4", "Demo Ng WiFi Client Easy Fox", dl,
                                     [1], lambda c: None, clock=clock)
        self.assertEqual(probes.count, 1)
        self.assertFalse(probes.carried("Demo Ng WiFi Client Easy Fox"))
        self.assertEqual(probes.other_ssids("Demo Ng WiFi Client Easy Fox"), [])

    def test_tshark_exit_is_a_run_error(self):
        dl, clock = deadline(10)
        reader = FakeReader(wifi.CLIENT_FIELDS, [(0.1, None)], clock)
        with self.assertRaises(RunError):
            wifi.collect_probes(reader, "F2:44:5E:10:97:F4", "x", dl, [1], lambda c: None, clock=clock)


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.report = report.Report(out=io.StringIO())

    def verdicts(self):
        return {row.value: row.verdict for row in self.report.rows}

    def test_ap_rows_pass(self):
        block = conf.select(HEADER, ["AP", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_ap.log"))
        wifi.ap_rows(self.report, block, readback, beacon(0))
        self.assertEqual(self.verdicts(), {"MAC_ADDR": "pass", "CHANNEL": "pass", "FSSID": "pass",
                                           "SSID_HIDDEN": "pass", "SECURITY": "pass"})
        self.assertEqual(self.report.rows[4].air, "WPA2-PSK/CCMP")

    def test_ap_rows_random_channel_accepts_the_fox_choice(self):
        block = conf.select(HEADER, ["AP", "HARD"])
        readback = parse_transcript("Fox: wifi_ap_client HARD AP\nStarted AP with MAC Address: F2:72:C1:79:16:1B\n"
                                    "Operating channel: 6\nOperating SSID: Demo YT WiFi AP Hard Fox\n"
                                    "Hidden SSID: 0\n")
        b = beacon(1)._replace(ssid="Demo YT WiFi AP Hard Fox")
        wifi.ap_rows(self.report, block, readback, b)
        rows = {row.value: row for row in self.report.rows}
        self.assertEqual(rows["CHANNEL"].header, "random")
        self.assertEqual(rows["CHANNEL"].verdict, "pass")
        self.assertEqual(rows["FSSID"].verdict, "pass")

    def test_ap_rows_hidden_network_keeps_the_name_on_serial(self):
        block = conf.select(HEADER, ["AP", "HARD"])
        text = HEADER.replace("#define SSID_HIDDEN 0", "#define SSID_HIDDEN 1")
        block = conf.select(text, ["AP", "HARD"])
        readback = parse_transcript("Started AP with MAC Address: F2:72:C1:79:16:1B\nOperating channel: 6\n"
                                    "Operating SSID: Demo YT WiFi AP Hard Fox\nHidden SSID: 1\n")
        wifi.ap_rows(self.report, block, readback, beacon(1))
        rows = {row.value: row for row in self.report.rows}
        self.assertEqual(rows["FSSID"].verdict, "serial")
        self.assertEqual(rows["SSID_HIDDEN"].verdict, "pass")
        self.assertEqual(rows["SSID_HIDDEN"].air, "1")

    def test_ap_rows_without_a_beacon_are_unverified(self):
        block = conf.select(HEADER, ["AP", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_ap.log"))
        wifi.ap_rows(self.report, block, readback, None, "no beacon on channel 1")
        self.assertEqual(set(self.verdicts().values()), {"unverified"})
        self.assertEqual(self.report.rows[0].reason, "no beacon on channel 1")

    def test_ap_rows_fail_on_wrong_ssid_and_security(self):
        block = conf.select(HEADER, ["AP", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_ap.log"))
        wifi.ap_rows(self.report, block, readback, beacon(3)._replace(bssid="F2:F4:90:22:0D:0F", ds_channel=1,
                                                                        ht_channel=1, frequency=2412))
        rows = {row.value: row for row in self.report.rows}
        self.assertEqual(rows["FSSID"].verdict, "FAIL")
        self.assertEqual(rows["FSSID"].air, "Coffee")
        self.assertEqual(rows["SECURITY"].verdict, "FAIL")
        self.assertEqual(rows["MAC_ADDR"].verdict, "pass")

    def test_client_rows(self):
        block = conf.select(HEADER, ["CLIENT", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_client.log"))
        probes = wifi.Probes("F2:44:5E:10:97:F4", 2, [None, "Demo Ng WiFi Client Easy Fox"], [1], 1.0)
        wifi.client_rows(self.report, block, readback, probes)
        self.assertEqual(self.verdicts(), {"MAC_ADDR": "pass", "FSSID": "pass"})

    def test_client_rows_without_the_ssid(self):
        block = conf.select(HEADER, ["CLIENT", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_client.log"))
        wifi.client_rows(self.report, block, readback, wifi.Probes("F2:44:5E:10:97:F4", 3, [None, None, None], [1], 1.0))
        self.assertEqual(self.report.rows[1].verdict, "unverified")
        self.assertIn("3 probe requests", self.report.rows[1].reason)
        self.report.rows.clear()
        wifi.client_rows(self.report, block, readback, wifi.Probes("F2:44:5E:10:97:F4", 1, ["Other"], [1], 1.0))
        self.assertEqual(self.report.rows[1].verdict, "FAIL")
        self.assertEqual(self.report.rows[1].air, "Other")
        self.report.rows.clear()
        wifi.client_rows(self.report, block, readback, None, "no sniffer")
        self.assertEqual([row.verdict for row in self.report.rows], ["unverified", "unverified"])


class InterfaceStateTest(unittest.TestCase):
    def setUp(self):
        self.net = tempfile.mkdtemp(prefix="foxverify-net-")
        self.addCleanup(shutil.rmtree, self.net)
        os.makedirs(os.path.join(self.net, "wlan1"))
        with open(os.path.join(self.net, "wlan1", "flags"), "w") as handle:
            handle.write("0x1003\n")
        self.run = Recorder({"iw dev wlan1 info": "Interface wlan1\n\tifindex 3\n\ttype managed\n\tchannel 1\n"})

    def test_save_state(self):
        state = wifi.save_state("wlan1", self.run, self.net)
        self.assertEqual(state, wifi.InterfaceState("wlan1", "managed", True))

    def test_unknown_interface(self):
        with self.assertRaises(RunError):
            wifi.interface_up("wlan9", self.net)

    def test_monitor_mode_restores_on_exception(self):
        with self.assertRaises(ZeroDivisionError):
            with wifi.monitor_mode("wlan1", self.run, self.net, handle_signals=False) as state:
                self.assertEqual(state.type, "managed")
                self.assertEqual(self.run.calls[-1], ["ip", "link", "set", "wlan1", "up"])
                wifi.set_channel("wlan1", 6, self.run)
                1 / 0
        self.assertEqual(self.run.calls[-4:], [
            ["iw", "dev", "wlan1", "set", "channel", "6"],
            ["ip", "link", "set", "wlan1", "down"],
            ["iw", "dev", "wlan1", "set", "type", "managed"],
            ["ip", "link", "set", "wlan1", "up"],
        ])
        self.assertEqual(self.run.calls[1:4], [
            ["ip", "link", "set", "wlan1", "down"],
            ["iw", "dev", "wlan1", "set", "type", "monitor"],
            ["ip", "link", "set", "wlan1", "up"],
        ])

    def test_monitor_mode_leaves_a_down_interface_down(self):
        with open(os.path.join(self.net, "wlan1", "flags"), "w") as handle:
            handle.write("0x1002\n")
        with wifi.monitor_mode("wlan1", self.run, self.net, handle_signals=False):
            pass
        self.assertEqual(self.run.calls[-2:], [
            ["ip", "link", "set", "wlan1", "down"],
            ["iw", "dev", "wlan1", "set", "type", "managed"],
        ])

    def test_failed_command_is_a_run_error_with_stderr(self):
        failing = Recorder(self.run.answers,
                           {"iw dev wlan1 set type monitor": Recorder.Result(240, "", "command failed: Operation not supported (-95)")})
        with self.assertRaises(RunError) as caught:
            with wifi.monitor_mode("wlan1", failing, self.net, handle_signals=False):
                pass
        self.assertIn("Operation not supported", str(caught.exception))
        # The failed switch still restores what was saved.
        self.assertEqual(failing.calls[-1], ["ip", "link", "set", "wlan1", "up"])

    def test_signal_handlers_are_put_back(self):
        import signal
        before = signal.getsignal(signal.SIGTERM)
        with wifi.monitor_mode("wlan1", self.run, self.net):
            self.assertIs(signal.getsignal(signal.SIGTERM), wifi._raise_terminated)
        self.assertIs(signal.getsignal(signal.SIGTERM), before)


class DeadlineUseTest(unittest.TestCase):
    def test_observe_ap_tunes_then_reads(self):
        """observe_ap with a fake popen that plays tshark through a real pipe."""
        import subprocess
        import sys
        dl = Deadline(60)
        run = Recorder()
        script = "import sys; sys.stdout.write(%r); sys.stdout.flush()" % (BEACONS[0] + "\n")

        def popen(argv, **kwargs):
            self.assertEqual(argv[1:3], ["-i", "wlan1"])
            return subprocess.Popen([sys.executable, "-c", script], **kwargs)

        b = wifi.observe_ap("wlan1", "F2:F4:90:22:0D:0F", 1, dl, "tshark", run, popen)
        self.assertEqual(run.calls, [["iw", "dev", "wlan1", "set", "channel", "1"]])
        self.assertEqual(b.bssid, "F2:F4:90:22:0D:0F")


if __name__ == "__main__":
    unittest.main()
