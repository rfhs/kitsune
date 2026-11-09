import os
import tempfile
import unittest
from unittest import mock

from foxverify import serial_fox
from foxverify.report import Deadline, RunError
from foxverify.tests import fixture, frozen_text, read_fixture

PROJECT_DIRS = {
    "classic_discoverable": "bluetooth/classic_discoverable",
    "iBeacon": "bluetooth/iBeacon",
    "wifi_ap_client": "wifi/wifi_ap_client",
    "zigbee_coordinator": "zigbee/zigbee_coordinator",
}

TIMERS = {"time_to_wake": "TIME_TO_WAKE", "time_to_sleep": "TIME_TO_SLEEP"}
WIFI_COMMON = dict(TIMERS, mac="MAC_ADDR", ssid="FSSID", psk="PSK", tx_power="TXPOWER")
WIFI_AP = dict(WIFI_COMMON, ssid_hidden="SSID_HIDDEN", max_clients="MAX_CLIENTS")
ZIGBEE = dict(TIMERS, mac="MAC_ADDR", channel="CHANNEL", pan_id="PAN_ID", ext_pan_id="EXT_PAN_ID",
              packet_interval="PACKET_INTERVAL", tx_power="TXPOWER")
IBEACON = dict(TIMERS, name="DEVICE_NAME", uuid="BEACON_UUID", major="MAJOR", minor="MINOR",
               address="MAC_ADDR", tx_power="TXPOWER")

# transcript -> (project, difficulty, mode, serial field -> header macro)
TRANSCRIPTS = {
    "classic_easy": ("classic_discoverable", "EASY", None,
                     dict(TIMERS, name="NAME", address="MAC_ADDR")),
    "classic_hard": ("classic_discoverable", "HARD", None,
                     dict(TIMERS, name="NAME", address="MAC_ADDR")),
    "ibeacon_easy": ("iBeacon", "EASY", None, IBEACON),
    "ibeacon_medium": ("iBeacon", "MEDIUM", None, IBEACON),
    "ibeacon_hard": ("iBeacon", "HARD", None, IBEACON),
    "wifi_easy_ap": ("wifi_ap_client", "EASY", "AP", dict(WIFI_AP, channel="CHANNEL")),
    "wifi_hard_ap": ("wifi_ap_client", "HARD", "AP", WIFI_AP),
    "wifi_fiveeasy_ap": ("wifi_ap_client", "FIVEEASY", "AP", dict(WIFI_AP, channel="CHANNEL")),
    "wifi_fivehard_ap": ("wifi_ap_client", "FIVEHARD", "AP", WIFI_AP),
    "wifi_easy_client": ("wifi_ap_client", "EASY", "CLIENT", WIFI_COMMON),
    "wifi_hard_client": ("wifi_ap_client", "HARD", "CLIENT", WIFI_COMMON),
    "zigbee_easy": ("zigbee_coordinator", "EASY", None, ZIGBEE),
    "zigbee_hard": ("zigbee_coordinator", "HARD", None, ZIGBEE),
}


def transcript(name):
    return read_fixture("transcripts", name + ".log")


def timed(text, first=1.0, step=0.05):
    """A transcript as (delay, line) items: ``first`` seconds to the first
    line, ``step`` between the rest."""
    lines = text.splitlines(True)
    return [((first if i == 0 else step), line) for i, line in enumerate(lines)]


class Run:
    """One read_fox call against a replayed transcript on a fake clock."""

    def __init__(self, items, reset=True, timeout=60.0):
        self.clock = serial_fox.FakeClock()
        self.deadline = Deadline(timeout, self.clock)
        self.source = serial_fox.TranscriptSource(items, self.clock)
        self.said = []
        self.debugged = []
        self.readback = None
        self.error = None
        try:
            self.readback = serial_fox.read_fox(self.source, self.deadline, reset,
                                                self.said.append, self.debugged.append)
        except RunError as error:
            self.error = error

    def elapsed(self):
        return self.clock.now - self.deadline.started


class BannerTest(unittest.TestCase):
    def test_banner_forms(self):
        for text, expected in [
            ("Fox: classic_discoverable HARD", ("classic_discoverable", "HARD", None)),
            ("Fox: iBeacon MEDIUM", ("iBeacon", "MEDIUM", None)),
            ("Fox: wifi_ap_client EASY AP", ("wifi_ap_client", "EASY", "AP")),
            ("Fox: wifi_ap_client FIVEHARD AP", ("wifi_ap_client", "FIVEHARD", "AP")),
            ("Fox: wifi_ap_client HARD CLIENT", ("wifi_ap_client", "HARD", "CLIENT")),
            ("Fox: zigbee_coordinator EASY", ("zigbee_coordinator", "EASY", None)),
        ]:
            readback = serial_fox.parse_transcript(text + "\r\n")
            self.assertEqual(readback.banner, serial_fox.Banner(*expected), text)
            self.assertEqual(readback.banner.text(), text)

    def test_lines_that_are_not_a_banner(self):
        for text in ("Fox: wifi_ap_client", "Fox: iBeacon medium", "Fox: iBeacon EASY AP CLIENT",
                     "Fox:zigbee_coordinator EASY", " Fox: iBeacon EASY", "Fox: iBeacon EASY trailing"):
            self.assertIsNone(serial_fox.parse_transcript(text + "\n").banner, text)


class TranscriptTest(unittest.TestCase):
    """Every recorded transcript parses and agrees with its demo header."""

    def test_every_project_and_difficulty(self):
        for name, (project, difficulty, mode, fields) in TRANSCRIPTS.items():
            readback = serial_fox.parse_transcript(transcript(name))
            self.assertEqual(readback.banner, serial_fox.Banner(project, difficulty, mode), name)
            self.assertFalse(readback.halted(), name)
            self.assertTrue(readback.complete(), name)
            self.assertEqual(readback.get("initializing"), "Initializing...", name)
            self.assertIsNotNone(readback.integer("boot_count"), name)
            self.assertIn("since cold boot", readback.get("sleep_stats"), name)
            block = serial_fox.block_for(readback, project, frozen_text(project))
            for field, macro in fields.items():
                value = readback.get(field)
                self.assertIsNotNone(value, "%s: %s" % (name, field))
                text = block.raw(macro)
                if text.startswith('"'):
                    self.assertEqual(value, block.string(macro), "%s: %s" % (name, field))
                elif text.startswith("{") or macro == "EXT_PAN_ID":
                    self.assertTrue(serial_fox.same_mac(block.mac(macro), value), "%s: %s" % (name, field))
                elif text.startswith(("WIFI_POWER_", "ESP_PWR_LVL_")):
                    self.assertEqual(value, block.identifier(macro), "%s: %s" % (name, field))
                else:
                    self.assertEqual(readback.integer(field), block.integer(macro), "%s: %s" % (name, field))

    def test_crlf_line_endings(self):
        text = transcript("zigbee_easy").replace("\n", "\r\n")
        readback = serial_fox.parse_transcript(text)
        self.assertEqual(readback.banner.project, "zigbee_coordinator")
        self.assertEqual(readback.get("pan_id"), "0x1337")
        self.assertEqual(readback.integer("pan_id"), 0x1337)
        self.assertEqual(readback.get("short_address"), "0x0000")
        self.assertEqual(readback.integer("packet_interval"), 1)
        self.assertEqual(readback.get("setting_up"), "Zigbee Coordinator")
        self.assertEqual(readback.get("mac_set"), "successfully")
        self.assertEqual(readback.get("awake"), "Awake and screaming")
        self.assertFalse(any("\r" in line for line in readback.lines))

    def test_wifi_fields(self):
        readback = serial_fox.parse_transcript(transcript("wifi_easy_ap"))
        self.assertEqual(readback.get("setting_up"), "AP (Access Point)")
        self.assertEqual(readback.get("tx_power_status"), "ok")
        self.assertEqual(readback.get("mac"), "F2:F4:90:22:0D:0F")
        self.assertEqual(readback.integer("channel"), 1)
        self.assertEqual(readback.get("ssid"), "Demo Hiro WiFi AP Easy Fox")
        self.assertEqual(readback.get("psk"), "0123456789")
        self.assertEqual(readback.integer("ssid_hidden"), 0)
        self.assertEqual(readback.integer("max_clients"), 1)
        self.assertEqual(readback.get("tx_power"), "WIFI_POWER_17dBm")
        self.assertEqual(readback.integer("time_to_wake"), 15)
        self.assertEqual(readback.integer("time_to_sleep"), 5)
        client = serial_fox.parse_transcript(transcript("wifi_hard_client"))
        self.assertEqual(client.get("setting_up"), "WiFi Client")
        self.assertEqual(client.get("mac"), "F2:83:27:31:80:C7")
        self.assertIsNone(client.get("channel"))
        self.assertEqual(client.get("ssid"), "Demo Mr Lee WiFi Client Hard Fox")
        self.assertEqual(client.get("psk"), "0123456789")
        self.assertIsNone(client.get("ssid_hidden"))
        self.assertIsNone(client.get("max_clients"))

    def test_zigbee_and_classic_power_and_timers(self):
        zigbee = serial_fox.parse_transcript(transcript("zigbee_hard"))
        self.assertEqual(zigbee.get("tx_power"), "20")
        self.assertEqual(zigbee.integer("tx_power"), 20)
        self.assertEqual(zigbee.integer("time_to_wake"), 300)
        self.assertEqual(zigbee.integer("time_to_sleep"), 1)
        negative = serial_fox.parse_transcript("Tx power: -15 dBm\n")
        self.assertEqual(negative.integer("tx_power"), -15)
        classic = serial_fox.parse_transcript(transcript("classic_hard"))
        self.assertEqual(classic.integer("time_to_wake"), 30)
        self.assertEqual(classic.integer("time_to_sleep"), 30)
        self.assertIsNone(classic.get("tx_power"))

    def test_ibeacon_fields(self):
        readback = serial_fox.parse_transcript(transcript("ibeacon_hard"))
        self.assertEqual(readback.get("name"), "Demo 3Jane BLE Hard Fox")
        self.assertEqual(readback.upper("uuid"), "DB6A0ED0-1DC3-4348-BD78-E997A0C082A3")
        self.assertEqual(readback.integer("major"), 5)
        self.assertEqual(readback.integer("minor"), 88)
        self.assertEqual(readback.integer("signal_power"), -59)
        self.assertEqual(readback.get("address"), "F2:AC:87:05:0A:C7")
        self.assertEqual(readback.get("tx_power"), "ESP_PWR_LVL_N12")
        self.assertEqual(readback.integer("time_to_wake"), 10)
        self.assertEqual(readback.integer("time_to_sleep"), 30)
        self.assertEqual(readback.get("advertising"), "iBeacon advertising!")
        self.assertEqual(readback.get("sleeping"), "entering deep sleep")
        easy = serial_fox.parse_transcript(transcript("ibeacon_easy"))
        self.assertEqual(easy.get("tx_power"), "ESP_PWR_LVL_P9")
        self.assertEqual(easy.integer("time_to_wake"), 300)
        self.assertEqual(easy.integer("time_to_sleep"), 0)
        self.assertIsNone(easy.get("sleeping"))
        mismatch = serial_fox.parse_transcript("Tx power: ESP_PWR_LVL_P3 (3 dBm)\n"
                                               "Requested tx power: ESP_PWR_LVL_N0 (0 dBm)\n"
                                               "Tx power != Requested tx power\nPANIC\n")
        self.assertEqual(mismatch.get("tx_power"), "ESP_PWR_LVL_P3")
        self.assertEqual(mismatch.get("requested:tx power"), "ESP_PWR_LVL_N0 (0 dBm)")
        self.assertEqual(mismatch.problems, ["Tx power != Requested tx power", "PANIC"])

    def test_classic_fields(self):
        readback = serial_fox.parse_transcript(transcript("classic_hard"))
        self.assertEqual(readback.get("name"), "Demo Case BTC Hard Fox")
        self.assertEqual(readback.get("address"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(readback.get("sleeping"), "Going to sleep")
        self.assertEqual(readback.integer("boot_count"), 4)
        self.assertTrue(any(line.startswith("rst:0x1") for line in readback.unmatched))

    def test_mismatch_transcripts_halt(self):
        zigbee = serial_fox.parse_transcript(transcript("zigbee_easy_mismatch"))
        self.assertTrue(zigbee.halted())
        self.assertTrue(zigbee.complete())
        self.assertEqual(zigbee.problems, ["Operating PAN ID != Requested PAN ID", "PANIC"])
        self.assertEqual(zigbee.get("pan_id"), "0x1234")
        self.assertEqual(zigbee.get("requested:pan id"), "0x1337")
        self.assertIsNone(zigbee.get("awake"))
        classic = serial_fox.parse_transcript(transcript("classic_easy_mismatch"))
        self.assertTrue(classic.halted())
        self.assertEqual(classic.get("address"), "F2:81:5A:C1:A3:28")
        self.assertEqual(classic.get("requested:address"), "F2:81:5A:C1:A3:26")
        self.assertIn("Device address != Requested address", classic.problems)

    def test_other_problem_lines(self):
        for line in ("Error starting Zigbee", "Error setting MAC address",
                     "Error setting packet interval: ESP_ERR_INVALID_ARG",
                     "Device address: unavailable, the Bluetooth stack is not enabled",
                     "Beacon data is 0 bytes, not 25", "Entered loop, we are broken",
                     "Read MAC Address != Requested Mac Address", "Short address != 0x0000"):
            readback = serial_fox.parse_transcript(line + "\n")
            self.assertEqual(readback.problems, [line], line)

    def test_rom_boot_and_empty_have_no_banner(self):
        rom = serial_fox.parse_transcript(transcript("rom_boot_only"))
        self.assertIsNone(rom.banner)
        self.assertEqual(rom.fields, {})
        self.assertEqual(len(rom.unmatched), len(transcript("rom_boot_only").splitlines()))
        self.assertFalse(rom.complete())
        empty = serial_fox.parse_transcript(transcript("empty"))
        self.assertEqual(empty.lines, [])
        self.assertIsNone(empty.banner)
        self.assertEqual(empty.transcript(), "")

    def test_transcript_round_trip(self):
        text = transcript("ibeacon_medium")
        readback = serial_fox.parse_transcript(text)
        self.assertEqual(readback.transcript(), text)


class BlockForTest(unittest.TestCase):
    def test_wrong_project_names_the_other_script(self):
        readback = serial_fox.parse_transcript(transcript("zigbee_easy"))
        with self.assertRaises(RunError) as caught:
            serial_fox.block_for(readback, "wifi_ap_client", frozen_text("wifi_ap_client"))
        self.assertEqual(str(caught.exception),
                         "this is a zigbee_coordinator fox; run zigbee/zigbee_coordinator/verify")
        self.assertEqual(caught.exception.exit_code, 2)

    def test_every_wrong_project_text(self):
        for project, directory in PROJECT_DIRS.items():
            self.assertEqual(serial_fox.wrong_project(project), "this is a %s fox; run %s/verify" % (project, directory))

    def test_missing_block_is_named(self):
        readback = serial_fox.parse_transcript(transcript("wifi_hard_ap"))
        header = frozen_text("wifi_ap_client").replace("#if defined(HARD)", "#if defined(NEVER)")
        with self.assertRaises(RunError) as caught:
            serial_fox.block_for(readback, "wifi_ap_client", header)
        self.assertEqual(str(caught.exception),
                         "src/current_conf.h has no HARD AP block; the fox was built with -D HARD -D AP")
        readback = serial_fox.parse_transcript(transcript("ibeacon_medium"))
        header = frozen_text("classic_discoverable")
        with self.assertRaises(RunError) as caught:
            serial_fox.block_for(readback, "iBeacon", header)
        self.assertEqual(str(caught.exception),
                         "src/current_conf.h has no MEDIUM block; the fox was built with -D MEDIUM")

    def test_no_banner_is_the_no_banner_outcome(self):
        readback = serial_fox.parse_transcript(transcript("rom_boot_only"))
        with self.assertRaises(RunError) as caught:
            serial_fox.block_for(readback, "iBeacon", "")
        self.assertEqual(str(caught.exception), serial_fox.NO_BANNER)

    def test_unparsable_header(self):
        readback = serial_fox.parse_transcript(transcript("classic_easy"))
        with self.assertRaises(RunError) as caught:
            serial_fox.block_for(readback, "classic_discoverable", "#if defined(EASY)\n#define MAC_ADDR {1}\n")
        self.assertIn("cannot parse src/current_conf.h", str(caught.exception))

    def test_header_mac_against_serial_mac(self):
        readback = serial_fox.parse_transcript(transcript("classic_easy_mismatch"))
        block = serial_fox.block_for(readback, "classic_discoverable", frozen_text("classic_discoverable"))
        self.assertFalse(serial_fox.same_mac(block.mac("MAC_ADDR"), readback.get("address")))
        self.assertTrue(serial_fox.same_mac("f2:81:5a:c1:a3:26", "F2:81:5A:C1:A3:26"))
        self.assertFalse(serial_fox.same_mac("F2:81:5A:C1:A3:26", None))
        self.assertEqual(serial_fox.DIFFERENT_HEADER,
                         "fox was built from a different conference header than src/current_conf.h")


class ReadFoxTest(unittest.TestCase):
    def test_reads_to_the_last_line_after_a_reset(self):
        run = Run(timed(transcript("classic_easy")))
        self.assertIsNone(run.error)
        self.assertEqual(run.source.resets, 1)
        self.assertTrue(run.readback.complete())
        self.assertEqual(run.readback.get("address"), "F2:81:5A:C1:A3:26")
        self.assertEqual(run.said, ["Fox: classic_discoverable EASY"])
        self.assertLess(run.elapsed(), 3.0)
        self.assertTrue(any("resetting the fox" in line for line in run.debugged))

    def test_every_transcript_completes_within_a_few_seconds(self):
        for name in TRANSCRIPTS:
            run = Run(timed(transcript(name)))
            self.assertIsNone(run.error, name)
            self.assertTrue(run.readback.complete(), name)
            self.assertLess(run.elapsed(), 4.0, name)

    def test_empty_transcript_is_no_output(self):
        run = Run(timed(transcript("empty")))
        self.assertEqual(str(run.error), serial_fox.NO_OUTPUT)
        self.assertEqual(run.error.exit_code, 2)
        self.assertEqual(run.elapsed(), 60.0)
        self.assertEqual(len(run.said), 1)
        self.assertTrue(run.said[0].startswith(serial_fox.NO_OUTPUT))
        self.assertIn("press its reset button", run.said[0])

    def test_hint_comes_at_ten_seconds_and_a_late_fox_still_counts(self):
        run = Run(timed(transcript("ibeacon_easy"), first=25.0))
        self.assertIsNone(run.error)
        self.assertEqual(len(run.said), 2)
        self.assertIn("press its reset button", run.said[0])
        self.assertEqual(run.said[1], "Fox: iBeacon EASY")
        self.assertTrue(run.readback.complete())

    def test_rom_boot_without_banner_is_not_a_fox(self):
        run = Run(timed(transcript("rom_boot_only")))
        self.assertEqual(str(run.error), serial_fox.NO_BANNER)
        self.assertEqual(run.error.exit_code, 2)
        self.assertAlmostEqual(run.elapsed(), 1.0 + serial_fox.NO_BANNER_SECONDS, places=3)

    def test_old_build_without_banner_is_not_a_fox(self):
        run = Run(timed(transcript("old_build_no_banner")))
        self.assertEqual(str(run.error), serial_fox.NO_BANNER)

    def test_garbage_counts_as_output(self):
        run = Run([(0.5, "\xfe\xfe\x00garbage at the wrong baud")])
        self.assertEqual(str(run.error), serial_fox.NO_BANNER)
        self.assertAlmostEqual(run.elapsed(), 0.5 + serial_fox.NO_BANNER_SECONDS, places=3)

    def test_banner_arriving_late_but_before_the_fifteen_seconds(self):
        items = timed(transcript("zigbee_easy"), first=1.0, step=0.05)
        banner_index = next(i for i, (_, line) in enumerate(items) if line.startswith("Fox:"))
        items[banner_index] = (12.0, items[banner_index][1])
        run = Run(items)
        self.assertIsNone(run.error)
        self.assertEqual(run.readback.banner.project, "zigbee_coordinator")

    def test_quiet_after_the_banner_ends_the_read(self):
        lines = ["Initializing...\n", "Fox: classic_discoverable EASY\n", "Device name: Demo Molly BTC Easy Fox\n"]
        run = Run(timed("".join(lines)))
        self.assertIsNone(run.error)
        self.assertFalse(run.readback.complete())
        self.assertEqual(run.readback.get("name"), "Demo Molly BTC Easy Fox")
        self.assertIsNone(run.readback.get("address"))
        self.assertAlmostEqual(run.elapsed(), 1.0 + 0.1 + serial_fox.QUIET_SECONDS, places=3)

    def test_problem_line_ends_the_read(self):
        run = Run(timed(transcript("zigbee_easy_mismatch")))
        self.assertIsNone(run.error)
        self.assertTrue(run.readback.halted())
        self.assertLess(run.elapsed(), 3.0)

    def test_no_reset_waits_for_the_natural_wake(self):
        run = Run(timed(transcript("wifi_easy_ap"), first=40.0), reset=False)
        self.assertIsNone(run.error)
        self.assertEqual(run.source.resets, 0)
        self.assertEqual(run.said, ["Fox: wifi_ap_client EASY AP"])
        self.assertTrue(run.readback.complete())

    def test_no_reset_outcomes_at_the_deadline(self):
        run = Run([], reset=False, timeout=30.0)
        self.assertEqual(str(run.error), serial_fox.NO_OUTPUT_NO_RESET)
        self.assertEqual(run.elapsed(), 30.0)
        self.assertEqual(run.said, [])
        run = Run([(1.0, "Going to sleep\n")], reset=False, timeout=30.0)
        self.assertEqual(str(run.error), serial_fox.NO_BANNER_NO_RESET)
        self.assertEqual(run.elapsed(), 30.0)

    def test_deadline_during_the_readback_keeps_what_arrived(self):
        items = timed(transcript("zigbee_easy"), first=1.0, step=1.0)
        run = Run(items, timeout=len(items) - 3.0)
        self.assertIsNone(run.error)
        self.assertIsNotNone(run.readback.banner)
        self.assertFalse(run.readback.complete())

    def test_partial_last_line_without_newline_is_kept(self):
        run = Run([(1.0, "Fox: iBeacon EASY\n"), (0.1, "Device name: Demo Bruce BLE Easy Fox")])
        self.assertEqual(run.readback.get("name"), "Demo Bruce BLE Easy Fox")

    def test_port_gone_is_reopened(self):
        class Vanishing(serial_fox.TranscriptSource):
            def read(self, timeout):
                if self.resets and not self.reopens:
                    raise serial_fox.PortGone("gone")
                return super().read(timeout)

        clock = serial_fox.FakeClock()
        source = Vanishing(timed(transcript("ibeacon_medium")), clock)
        readback = serial_fox.read_fox(source, Deadline(60, clock))
        self.assertEqual(source.reopens, 1)
        self.assertTrue(readback.complete())


class TranscriptSourceTest(unittest.TestCase):
    def test_from_file_and_delays(self):
        clock = serial_fox.FakeClock()
        source = serial_fox.TranscriptSource.from_file(fixture("transcripts", "classic_easy.log"), clock=clock)
        self.assertEqual(source.path, fixture("transcripts", "classic_easy.log"))
        first = source.read(5.0)
        self.assertEqual(first, "ets Jul 29 2019 12:21:46\n")
        self.assertEqual(clock.now, 1000.0)
        source.items = [(3.0, "late\n")]
        self.assertIsNone(source.read(1.0))
        self.assertEqual(clock.now, 1001.0)
        self.assertEqual(source.read(5.0), "late\n")
        self.assertEqual(clock.now, 1003.0)
        self.assertIsNone(source.read(2.5))
        self.assertEqual(clock.now, 1005.5)

    def test_real_clock_sleeps(self):
        slept = []
        source = serial_fox.TranscriptSource([(0.2, "x")], sleep=slept.append)
        self.assertEqual(source.read(1.0), "x\n")
        self.assertIsNone(source.read(0.3))
        self.assertEqual(slept, [0.2, 0.3])


class FakeSerial:
    """Records the order of line-state changes the way a port would see them."""

    instances = []

    def __init__(self):
        self.events = []
        self.port = None
        self.baudrate = None
        self.timeout = None
        self._dtr = None
        self._rts = None
        self.opened = False
        self.closed = False
        self.data = b""
        self.fail_read = None
        FakeSerial.instances.append(self)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self._dtr = value
        self.events.append(("dtr", value))

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        self._rts = value
        self.events.append(("rts", value))

    def open(self):
        self.opened = True
        self.events.append(("open",))

    def close(self):
        self.closed = True

    @property
    def in_waiting(self):
        return len(self.data)

    def read(self, size=1):
        if self.fail_read:
            raise self.fail_read
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class SerialSourceTest(unittest.TestCase):
    def setUp(self):
        FakeSerial.instances = []
        patcher = mock.patch("serial.Serial", FakeSerial)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.slept = []

    def source(self, path="/dev/ttyUSB0"):
        return serial_fox.SerialSource(path, sleep=self.slept.append)

    def test_open_asserts_dtr_then_rts_before_opening(self):
        source = self.source()
        port = FakeSerial.instances[0]
        self.assertEqual(port.port, "/dev/ttyUSB0")
        self.assertEqual(port.baudrate, 115200)
        self.assertEqual(port.events, [("dtr", True), ("rts", True), ("open",)])
        self.assertIs(source.serial, port)

    def test_reset_is_esptool_hard_reset_then_lines_asserted_again(self):
        source = self.source()
        port = FakeSerial.instances[0]
        del port.events[:]
        source.reset()
        self.assertEqual(port.events, [("dtr", False), ("rts", True), ("rts", False), ("dtr", True), ("rts", True)])
        self.assertEqual(self.slept, [serial_fox.RESET_PULSE_SECONDS, serial_fox.RESET_PULSE_SECONDS])

    def test_reset_survives_the_device_dropping_off_the_bus(self):
        source = self.source()
        port = FakeSerial.instances[0]

        class Dropping(FakeSerial):
            pass

        def failing_rts(self, value):
            raise OSError(5, "Input/output error")

        Dropping.rts = property(FakeSerial.rts.fget, failing_rts)
        port.__class__ = Dropping
        port.events = [("start",)]
        source.reset()
        self.assertEqual(port.events, [("start",), ("dtr", False)])

    def test_read_returns_text_or_none_and_raises_port_gone(self):
        source = self.source()
        port = FakeSerial.instances[0]
        self.assertIsNone(source.read(0.5))
        self.assertEqual(port.timeout, 0.5)
        port.data = b"Fox: iBeacon EASY\r\nDevice name: Demo\xe2\x80"
        self.assertEqual(source.read(0.5), "Fox: iBeacon EASY\r\nDevice name: Demo")
        port.data = b"\xa6!\r\n"
        self.assertEqual(source.read(0.5), "\u2026!\r\n")
        import serial
        port.fail_read = serial.SerialException("device reports readiness to read but returned no data")
        with self.assertRaises(serial_fox.PortGone):
            source.read(0.5)
        self.assertTrue(port.closed)
        self.assertIsNone(source.serial)
        with self.assertRaises(serial_fox.PortGone):
            source.read(0.5)

    def test_reopen_waits_for_the_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "ttyACM0")
            clock = serial_fox.FakeClock()
            source = serial_fox.SerialSource(path, sleep=clock.advance)
            source.close()
            with self.assertRaises(RunError) as caught:
                source.reopen(Deadline(1.0, clock))
            self.assertEqual(str(caught.exception), serial_fox.PORT_GONE)
            self.assertGreaterEqual(clock.now, 1001.0)
            with open(path, "w"):
                pass
            source.reopen(Deadline(1.0, clock))
            self.assertIsNotNone(source.serial)
            self.assertEqual(FakeSerial.instances[-1].events, [("dtr", True), ("rts", True), ("open",)])


if __name__ == "__main__":
    unittest.main()
