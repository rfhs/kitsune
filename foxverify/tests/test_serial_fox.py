import os
import tempfile
import unittest
from unittest import mock

from foxverify import devices, serial_fox, usbstack
from foxverify.report import Deadline, RunError
from foxverify.tests import fixture, frozen_text, read_fixture
from foxverify.tests.test_devices import CP210X, ESP, NANO, OTHER

PROJECT_DIRS = {
    "classic_discoverable": "bluetooth/classic_discoverable",
    "iBeacon": "bluetooth/iBeacon",
    "wifi_ap_client": "wifi/wifi_ap_client",
    "zigbee_coordinator": "zigbee/zigbee_coordinator",
}

# The fields every fox prints: the device address first, the timers after
# the banner.
COMMON = {"address": "MAC_ADDR", "time_to_wake": "TIME_TO_WAKE", "time_to_sleep": "TIME_TO_SLEEP"}
CLASSIC = dict(COMMON, name="NAME")
WIFI_COMMON = dict(COMMON, ssid="FSSID", psk="PSK", tx_power="TXPOWER")
WIFI_AP = dict(WIFI_COMMON, ssid_hidden="SSID_HIDDEN", max_clients="MAX_CLIENTS")
ZIGBEE = dict(COMMON, channel="CHANNEL", pan_id="PAN_ID", ext_pan_id="EXT_PAN_ID",
              packet_interval="PACKET_INTERVAL", tx_power="TXPOWER")
IBEACON = dict(COMMON, name="DEVICE_NAME", uuid="BEACON_UUID", major="MAJOR", minor="MINOR",
               tx_power="TXPOWER")

# transcript -> (project, difficulty, mode, serial field -> header macro)
TRANSCRIPTS = {
    "classic_easy": ("classic_discoverable", "EASY", None, CLASSIC),
    "classic_hard": ("classic_discoverable", "HARD", None, CLASSIC),
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


# The ROM's boot-mode line after a reset into download mode, from an ESP32-S3
# through its USB-Serial-JTAG port and from an ESP32 behind a UART bridge.
ROM_DOWNLOAD_S3 = "rst:0x1 (POWERON),boot:0x0 (DOWNLOAD(USB/UART0))\r\n"
ROM_DOWNLOAD_ESP32 = "rst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))\r\n"


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
            self.assertEqual(readback.get("mac_set"), "successfully", name)
            self.assertEqual(readback.get("awake"), "Awake and screaming", name)
            # Every line from the firmware's first one on has a regex; only
            # the ROM's boot text before it is unmatched.
            firmware = readback.lines[readback.lines.index("Initializing..."):]
            self.assertEqual([line for line in firmware if line in readback.unmatched], [], name)
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
        self.assertEqual(readback.get("setting_up"), "WiFi AP")
        self.assertEqual(readback.get("tx_power_status"), "ok")
        self.assertEqual(readback.get("address"), "F2:F4:90:22:0D:0F")
        self.assertEqual(readback.integer("channel"), 1)
        self.assertEqual(readback.get("ssid"), "Demo Hiro WiFi AP Easy Fox")
        self.assertEqual(readback.get("psk"), "0123456789")
        self.assertEqual(readback.integer("ssid_hidden"), 0)
        self.assertEqual(readback.integer("max_clients"), 1)
        self.assertEqual(readback.get("tx_power"), "WIFI_POWER_17dBm")
        self.assertEqual(readback.integer("time_to_wake"), 15)
        self.assertEqual(readback.integer("time_to_sleep"), 5)
        self.assertEqual(readback.get("last_cycle"), "20.0s, target 20s")
        client = serial_fox.parse_transcript(transcript("wifi_hard_client"))
        self.assertEqual(client.get("setting_up"), "WiFi Client")
        self.assertEqual(client.get("tx_power_status"), "ok")
        self.assertEqual(client.get("address"), "F2:83:27:31:80:C7")
        self.assertIsNone(client.get("channel"))
        self.assertEqual(client.get("ssid"), "Demo Mr Lee WiFi Client Hard Fox")
        self.assertEqual(client.get("psk"), "0123456789")
        self.assertIsNone(client.get("ssid_hidden"))
        self.assertIsNone(client.get("max_clients"))
        self.assertEqual(client.integer("time_to_sleep"), 0)
        self.assertEqual(client.get("last_cycle"), "301.4s, target 300s")

    def test_cycle_lines(self):
        """The informational lines of the exact cycle: "Last cycle" on a timer
        wake-up and "Cycle behind" after "Going to sleep" when the fox could
        not honour a non-zero TIME_TO_SLEEP."""
        behind = serial_fox.parse_transcript(transcript("wifi_fiveeasy_ap"))
        self.assertEqual(behind.get("last_cycle"), "21.3s, target 20s")
        self.assertEqual(behind.get("sleeping"), "Going to sleep")
        self.assertEqual(behind.get("cycle_behind"), "1.3")
        self.assertEqual(behind.lines[-2:], ["Going to sleep", "Cycle behind by 1.3s, rebooting at once"])
        self.assertFalse(behind.halted())
        self.assertTrue(behind.complete())
        for name in ("classic_easy", "ibeacon_easy", "wifi_easy_client", "zigbee_easy"):
            readback = serial_fox.parse_transcript(transcript(name))
            self.assertEqual(readback.integer("boot_count"), 0, name)
            self.assertIsNone(readback.get("last_cycle"), name)
            self.assertIsNone(readback.get("cycle_behind"), name)
        for name in ("classic_hard", "ibeacon_medium", "ibeacon_hard", "zigbee_hard"):
            readback = serial_fox.parse_transcript(transcript(name))
            self.assertGreater(readback.integer("boot_count"), 0, name)
            self.assertRegex(readback.get("last_cycle"), r"^\d+\.\ds, target \d+s$", name)
            self.assertIsNone(readback.get("cycle_behind"), name)

    def test_zigbee_and_classic_power_and_timers(self):
        zigbee = serial_fox.parse_transcript(transcript("zigbee_hard"))
        self.assertEqual(zigbee.get("setting_up"), "Zigbee Coordinator")
        self.assertEqual(zigbee.get("address"), "F2:A7:19:62:C3:08:BE:35")
        self.assertEqual(zigbee.get("tx_power"), "20")
        self.assertEqual(zigbee.integer("tx_power"), 20)
        self.assertEqual(zigbee.integer("time_to_wake"), 300)
        self.assertEqual(zigbee.integer("time_to_sleep"), 0)
        self.assertEqual(zigbee.get("last_cycle"), "304.2s, target 300s")
        negative = serial_fox.parse_transcript("Tx power: -15 dBm\n")
        self.assertEqual(negative.integer("tx_power"), -15)
        classic = serial_fox.parse_transcript(transcript("classic_hard"))
        self.assertEqual(classic.get("setting_up"), "Bluetooth Classic")
        self.assertEqual(classic.integer("time_to_wake"), 30)
        self.assertEqual(classic.integer("time_to_sleep"), 30)
        self.assertEqual(classic.get("last_cycle"), "60.0s, target 60s")
        self.assertIsNone(classic.get("tx_power"))

    def test_address_is_six_or_eight_bytes(self):
        for text, expected in [("Device address: F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:26"),
                               ("Device address: f2:5a:3c:91:0e:7b:44:d8", "f2:5a:3c:91:0e:7b:44:d8")]:
            self.assertEqual(serial_fox.parse_transcript(text + "\n").get("address"), expected, text)
        for text in ("Device address: F2:81:5A:C1:A3", "Device address: F2:81:5A:C1:A3:26:27",
                     "Device address: F2:81:5A:C1:A3:26:27:28:29", "Device address: F2-81-5A-C1-A3-26"):
            readback = serial_fox.parse_transcript(text + "\n")
            self.assertIsNone(readback.get("address"), text)
            self.assertEqual(readback.unmatched, [text], text)

    def test_ibeacon_fields(self):
        readback = serial_fox.parse_transcript(transcript("ibeacon_hard"))
        self.assertEqual(readback.get("setting_up"), "iBeacon")
        self.assertEqual(readback.get("address"), "F2:AC:87:05:0A:C7")
        self.assertEqual(readback.get("name"), "Demo 3Jane BLE Hard Fox")
        self.assertEqual(readback.upper("uuid"), "DB6A0ED0-1DC3-4348-BD78-E997A0C082A3")
        self.assertEqual(readback.integer("major"), 5)
        self.assertEqual(readback.integer("minor"), 88)
        self.assertEqual(readback.integer("signal_power"), -59)
        self.assertEqual(readback.get("tx_power"), "ESP_PWR_LVL_N12")
        self.assertEqual(readback.integer("time_to_wake"), 10)
        self.assertEqual(readback.integer("time_to_sleep"), 30)
        self.assertEqual(readback.get("awake"), "Awake and screaming")
        self.assertEqual(readback.get("sleeping"), "Going to sleep")
        easy = serial_fox.parse_transcript(transcript("ibeacon_easy"))
        self.assertEqual(easy.get("tx_power"), "ESP_PWR_LVL_P9")
        self.assertEqual(easy.integer("time_to_wake"), 300)
        self.assertEqual(easy.integer("time_to_sleep"), 0)
        self.assertIsNone(easy.get("sleeping"))
        mismatch = serial_fox.parse_transcript("Tx power: ESP_PWR_LVL_P3 (3 dBm)\n"
                                               "Requested tx power: ESP_PWR_LVL_N0 (0 dBm)\n"
                                               "Tx power != Requested tx power\n"
                                               "Fatal 2: readback mismatch\nPANIC\n")
        self.assertEqual(mismatch.get("tx_power"), "ESP_PWR_LVL_P3")
        self.assertEqual(mismatch.get("requested:tx power"), "ESP_PWR_LVL_N0 (0 dBm)")
        self.assertEqual(mismatch.problems, ["Tx power != Requested tx power", "Fatal 2: readback mismatch", "PANIC"])

    def test_classic_fields(self):
        readback = serial_fox.parse_transcript(transcript("classic_hard"))
        self.assertEqual(readback.get("address"), "F2:F6:6D:BC:2A:80")
        self.assertEqual(readback.get("name"), "Demo Case BTC Hard Fox")
        self.assertEqual(readback.get("awake"), "Awake and screaming")
        self.assertEqual(readback.get("sleeping"), "Going to sleep")
        self.assertEqual(readback.integer("boot_count"), 4)
        self.assertTrue(any(line.startswith("rst:0x5") for line in readback.unmatched))
        easy = serial_fox.parse_transcript(transcript("classic_easy"))
        self.assertIsNone(easy.get("sleeping"))
        self.assertTrue(any(line.startswith("rst:0x1") for line in easy.unmatched))

    def test_mismatch_transcripts_halt(self):
        zigbee = serial_fox.parse_transcript(transcript("zigbee_easy_mismatch"))
        self.assertTrue(zigbee.halted())
        self.assertTrue(zigbee.complete())
        self.assertEqual(zigbee.problems, ["Operating PAN ID != Requested PAN ID",
                                           "Fatal 2: readback mismatch", "PANIC"])
        self.assertEqual(zigbee.get("address"), "F2:5A:3C:91:0E:7B:44:D8")
        self.assertEqual(zigbee.get("pan_id"), "0x1234")
        self.assertEqual(zigbee.get("requested:pan id"), "0x1337")
        self.assertIsNone(zigbee.get("awake"))
        classic = serial_fox.parse_transcript(transcript("classic_easy_mismatch"))
        self.assertTrue(classic.halted())
        self.assertEqual(classic.get("address"), "F2:81:5A:C1:A3:28")
        self.assertEqual(classic.get("requested:address"), "F2:81:5A:C1:A3:26")
        self.assertIsNone(classic.get("name"))
        self.assertEqual(classic.problems, ["Device address != Requested address",
                                            "Fatal 2: readback mismatch", "PANIC"])

    def test_start_failure_transcript_halts_with_the_banner(self):
        """A radio start failure is printed before the banner, which
        rfhsfatal() prints on its own; the readback is a halted fox."""
        readback = serial_fox.parse_transcript(transcript("zigbee_start_failed"))
        self.assertEqual(readback.banner, serial_fox.Banner("zigbee_coordinator", "EASY", None))
        self.assertTrue(readback.halted())
        self.assertTrue(readback.complete())
        self.assertEqual(readback.problems, ["Error starting Zigbee", "Fatal 1: radio start failed", "PANIC"])
        self.assertEqual(readback.get("mac_set"), "successfully")
        self.assertIsNone(readback.get("address"))
        self.assertIsNone(readback.get("time_to_wake"))
        self.assertEqual(readback.lines.index("Error starting Zigbee") + 1,
                         readback.lines.index("Fox: zigbee_coordinator EASY"))

    def test_other_problem_lines(self):
        for line in ("Error starting Zigbee", "Error setting MAC address",
                     "Error setting packet interval: ESP_ERR_INVALID_ARG",
                     "Error setting country code: ESP_ERR_INVALID_ARG",
                     "Device address: unavailable, the Bluetooth stack is not enabled",
                     "Beacon data is 0 bytes, not 25",
                     "Fatal 1: radio start failed", "Fatal 2: readback mismatch",
                     "Fatal 3: deep sleep returned", "Fatal 4: loop() reached",
                     "Operating channel != Requested channel", "Extended PAN ID != Requested extended PAN ID",
                     "Short address != Requested short address"):
            readback = serial_fox.parse_transcript(line + "\n")
            self.assertEqual(readback.problems, [line], line)
        for line in ("Fatal: no code", "Fatality 2: readback mismatch", "PANIC!"):
            readback = serial_fox.parse_transcript(line + "\n")
            self.assertEqual(readback.problems, [], line)
            self.assertEqual(readback.unmatched, [line], line)

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
        lines = ["Initializing...\n", "Fox: classic_discoverable EASY\n", "Device address: F2:81:5A:C1:A3:26\n"]
        run = Run(timed("".join(lines)))
        self.assertIsNone(run.error)
        self.assertFalse(run.readback.complete())
        self.assertEqual(run.readback.get("address"), "F2:81:5A:C1:A3:26")
        self.assertIsNone(run.readback.get("name"))
        self.assertAlmostEqual(run.elapsed(), 1.0 + 0.1 + serial_fox.QUIET_SECONDS, places=3)

    def test_awake_line_ends_the_read_after_the_drain(self):
        """The read stops DRAIN_SECONDS after "Awake and screaming", so a
        line a fox prints later is not waited for."""
        items = timed(transcript("classic_hard"))
        awake = next(i for i, (_, line) in enumerate(items) if line.startswith("Awake"))
        items[awake + 1] = (30.0, items[awake + 1][1])
        run = Run(items)
        self.assertIsNone(run.error)
        self.assertTrue(run.readback.complete())
        self.assertEqual(run.readback.get("awake"), "Awake and screaming")
        self.assertIsNone(run.readback.get("sleeping"))
        self.assertAlmostEqual(run.elapsed(), 1.0 + 0.05 * awake + serial_fox.DRAIN_SECONDS, places=3)

    def test_problem_line_ends_the_read(self):
        run = Run(timed(transcript("zigbee_easy_mismatch")))
        self.assertIsNone(run.error)
        self.assertTrue(run.readback.halted())
        self.assertEqual(run.readback.problems, ["Operating PAN ID != Requested PAN ID"])
        self.assertLess(run.elapsed(), 3.0)

    def test_start_failure_is_read_up_to_the_banner(self):
        run = Run(timed(transcript("zigbee_start_failed")))
        self.assertIsNone(run.error)
        self.assertEqual(run.said, ["Fox: zigbee_coordinator EASY"])
        self.assertTrue(run.readback.halted())
        self.assertTrue(run.readback.complete())
        self.assertEqual(run.readback.problems, ["Error starting Zigbee"])
        self.assertEqual(run.readback.lines[-1], "Fox: zigbee_coordinator EASY")
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


    def test_bootloader_banner_is_answered_with_one_more_reset(self):
        """The ROM's download-mode lines after the reset mean the chip is in
        the bootloader; it is reset once more and the fox read as usual, the
        reset stamp being the second reset's."""
        items = [(0.5, ROM_DOWNLOAD_S3), (0.0, "waiting for download\n")] + timed(transcript("zigbee_easy"))
        run = Run(items)
        self.assertIsNone(run.error)
        self.assertEqual(run.source.resets, 2)
        self.assertEqual(run.said, [serial_fox.IN_BOOTLOADER, "Fox: zigbee_coordinator EASY"])
        self.assertTrue(run.readback.complete())
        self.assertEqual(run.readback.get("pan_id"), "0x1337")
        self.assertIn(ROM_DOWNLOAD_S3.strip(), run.readback.unmatched)
        self.assertIn("waiting for download", run.readback.unmatched)
        self.assertEqual(run.debugged.count("resetting the fox on transcript"), 1)
        self.assertLess(run.elapsed(), 4.0)

    def test_second_bootloader_banner_ends_the_run_with_the_hint(self):
        items = [(0.5, ROM_DOWNLOAD_S3), (0.0, "waiting for download\n"), (0.4, ROM_DOWNLOAD_S3),
                 (0.0, "waiting for download\n")] + timed(transcript("zigbee_easy"))
        run = Run(items)
        self.assertEqual(str(run.error), serial_fox.STILL_IN_BOOTLOADER)
        self.assertEqual(run.error.exit_code, 2)
        self.assertIn("press the board's reset button", str(run.error))
        self.assertEqual(run.source.resets, 2)
        self.assertEqual(run.said, [serial_fox.IN_BOOTLOADER])
        self.assertLess(run.elapsed(), 2.0)
        # The ESP32's bridge form of the lines is recognised too.
        run = Run([(0.5, ROM_DOWNLOAD_ESP32), (0.3, ROM_DOWNLOAD_ESP32)])
        self.assertEqual(str(run.error), serial_fox.STILL_IN_BOOTLOADER)

    def test_waiting_line_alone_triggers_the_reset_and_a_late_one_is_ignored(self):
        """Without the boot line only ``waiting for download`` is seen; one
        arriving after the second reset is the first boot's, still in flight,
        and does not count as a second failure."""
        items = [(0.5, "waiting for download\n"), (0.3, "waiting for download\n")] + timed(transcript("ibeacon_easy"))
        run = Run(items)
        self.assertIsNone(run.error)
        self.assertEqual(run.source.resets, 2)
        self.assertEqual(run.said, [serial_fox.IN_BOOTLOADER, "Fox: iBeacon EASY"])
        self.assertTrue(run.readback.complete())

    def test_bootloader_lines_without_a_reset_are_just_not_a_fox(self):
        run = Run([(0.5, ROM_DOWNLOAD_S3), (0.0, "waiting for download\n")], reset=False, timeout=20.0)
        self.assertEqual(run.source.resets, 0)
        self.assertEqual(run.said, [])
        self.assertEqual(str(run.error), serial_fox.NO_BANNER_NO_RESET)
        self.assertEqual(run.elapsed(), 20.0)

    def test_bootloader_lines_after_the_banner_are_ordinary_lines(self):
        items = timed(transcript("classic_easy")) + [(0.1, "waiting for download\n")]
        run = Run(items)
        self.assertIsNone(run.error)
        self.assertEqual(run.source.resets, 1)

    def test_source_without_a_reset_is_read_as_no_reset(self):
        """A USB stack that cannot reset the fox (the Nano's TinyUSB) is said
        and the read waits for the fox's own wake with no reset-button hint."""
        class NoReset(serial_fox.TranscriptSource):
            def reset(self, wall=None):
                return None

        clock = serial_fox.FakeClock()
        source = NoReset(timed(transcript("ibeacon_medium"), first=25.0), clock)
        said = []
        readback = serial_fox.read_fox(source, Deadline(60, clock), say=said.append)
        self.assertEqual(said, [serial_fox.NO_SERIAL_RESET, "Fox: iBeacon MEDIUM"])
        self.assertIsNone(readback.reset_time)
        self.assertIsNotNone(readback.banner_time)
        self.assertTrue(readback.complete())
        source = NoReset([], clock)
        with self.assertRaises(RunError) as caught:
            serial_fox.read_fox(source, Deadline(5, clock), say=said.append)
        self.assertEqual(str(caught.exception), serial_fox.NO_OUTPUT_NO_RESET)

    def test_reset_is_stamped_on_the_wall_clock(self):
        wall = serial_fox.FakeClock(1730000000.0)
        clock = serial_fox.FakeClock()
        source = serial_fox.TranscriptSource(timed(transcript("classic_hard")), clock)
        readback = serial_fox.read_fox(source, Deadline(60, clock), wall=wall)
        self.assertEqual(readback.reset_time, 1730000000.0)
        self.assertEqual(readback.banner_time, 1730000000.0)
        # The stamp is what the source's reset returns: the moment reset
        # was released, which a stamped source reports itself.
        class Released(serial_fox.TranscriptSource):
            def reset(self, wall=None):
                self.resets += 1
                return 42.5

        source = Released(timed(transcript("classic_hard")), clock)
        readback = serial_fox.read_fox(source, Deadline(60, clock), wall=wall)
        self.assertEqual(readback.reset_time, 42.5)
        source = serial_fox.TranscriptSource(timed(transcript("classic_hard")), clock)
        readback = serial_fox.read_fox(source, Deadline(60, clock), reset=False, wall=wall)
        self.assertIsNone(readback.reset_time)
        self.assertEqual(readback.banner_time, 1730000000.0)
        # On one clock the banner comes after the reset by the lines before it.
        source = serial_fox.TranscriptSource(timed(transcript("classic_hard")), clock)
        readback = serial_fox.read_fox(source, Deadline(60, clock), wall=clock)
        banner = next(i for i, line in enumerate(transcript("classic_hard").splitlines()) if line.startswith("Fox:"))
        self.assertAlmostEqual(readback.banner_time - readback.reset_time, 1.0 + 0.05 * banner, places=3)


class Vanishing(serial_fox.TranscriptSource):
    """A transcript source whose port goes away at a given clock time and is
    back ``away`` seconds later, as a native USB board's does in deep sleep."""

    def __init__(self, items, clock, gone_at, away):
        serial_fox.TranscriptSource.__init__(self, items, clock)
        self.gone_at = gone_at
        self.back_at = gone_at + away
        self.gone = False
        self.vanished = False

    def read(self, timeout):
        if not self.vanished and self.clock() >= self.gone_at:
            self.gone = self.vanished = True
            raise serial_fox.PortGone("gone")
        if self.gone:
            raise serial_fox.PortGone("still gone")
        return serial_fox.TranscriptSource.read(self, timeout)

    def try_open(self):
        if self.clock() < self.back_at:
            return False
        self.gone = False
        self.reopens += 1
        return True


class FollowerTest(unittest.TestCase):
    """The serial port read through the first sleep: the sleep line, the port
    vanishing, the reopen for wake 2's channel."""

    WAKE2 = ["Initializing...\n", "ESP32 boot count: 1\n", "Setting up WiFi AP...\n",
             "Fox: wifi_ap_client HARD AP\n", "Device address: F2:72:C1:79:16:1B\n",
             "Operating channel: 9\n", "Operating SSID: Demo YT WiFi AP Hard Fox\n"]

    def test_going_to_sleep_is_the_boundary_and_later_lines_are_wake_2(self):
        clock = serial_fox.FakeClock(0.0)
        source = serial_fox.TranscriptSource([(30.0, "Going to sleep\n"), (40.0, "Initializing...\n"),
                                              (1.0, "Operating channel: 9\n")], clock)
        follower = serial_fox.Follower(source, clock)
        follower.poll()
        self.assertIsNone(follower.boundary())
        clock.advance(29.9)
        follower.poll()
        self.assertIsNone(follower.boundary())
        clock.advance(0.2)
        follower.poll()
        self.assertAlmostEqual(follower.boundary(), 30.1)
        self.assertIsNone(follower.channel())
        clock.advance(41.0)
        follower.poll()
        follower.poll()
        self.assertEqual(follower.channel(), 9)
        self.assertEqual(follower.wake2.get("initializing"), "Initializing...")
        self.assertFalse(follower.gone)

    def test_lines_before_the_sleep_are_not_wake_2(self):
        clock = serial_fox.FakeClock(0.0)
        source = serial_fox.TranscriptSource([(1.0, "Operating channel: 7\n"), (2.0, "Going to sleep\n")], clock)
        follower = serial_fox.Follower(source, clock)
        clock.advance(5.0)
        follower.poll()
        follower.poll()
        self.assertIsNone(follower.channel())
        self.assertEqual(follower.boundary(), 5.0)

    def test_vanished_port_is_the_boundary_and_stays_closed_without_reopen(self):
        clock = serial_fox.FakeClock(0.0)
        source = Vanishing([(100.0, "never\n")], clock, gone_at=20.0, away=5.0)
        follower = serial_fox.Follower(source, clock)
        clock.advance(19.0)
        follower.poll()
        self.assertIsNone(follower.boundary())
        clock.advance(1.5)
        follower.poll()
        self.assertEqual(follower.boundary(), 20.5)
        self.assertTrue(follower.gone)
        clock.advance(30.0)
        follower.poll()
        self.assertTrue(follower.gone)
        self.assertEqual(source.reopens, 0)

    def test_reopen_reads_wake_2_channel(self):
        clock = serial_fox.FakeClock(0.0)
        items = [(26.0, line) if i == 0 else (0.1, line) for i, line in enumerate(self.WAKE2)]
        source = Vanishing(items, clock, gone_at=20.0, away=5.0)
        follower = serial_fox.Follower(source, clock, reopen=True)
        clock.advance(20.5)
        follower.poll()
        self.assertEqual(follower.boundary(), 20.5)
        clock.advance(2.0)
        follower.poll()
        self.assertTrue(follower.gone)
        self.assertEqual(source.reopens, 0)
        clock.advance(3.0)
        follower.poll()
        self.assertFalse(follower.gone)
        self.assertTrue(follower.reopened)
        self.assertEqual(source.reopens, 1)
        for _ in range(12):
            clock.advance(0.1)
            follower.poll()
        self.assertEqual(follower.channel(), 9)
        self.assertEqual(follower.wake2.banner.difficulty, "HARD")
        self.assertEqual(follower.pan_id(), None)

    def test_port_that_never_comes_back(self):
        clock = serial_fox.FakeClock(0.0)
        source = Vanishing([(100.0, "never\n")], clock, gone_at=20.0, away=1000.0)
        follower = serial_fox.Follower(source, clock, reopen=True)
        clock.advance(21.0)
        for _ in range(10):
            follower.poll()
            clock.advance(5.0)
        self.assertTrue(follower.gone)
        self.assertIsNone(follower.channel())
        self.assertEqual(follower.boundary(), 21.0)

    def test_zigbee_wake_2_pan_id(self):
        clock = serial_fox.FakeClock(0.0)
        source = serial_fox.TranscriptSource([(1.0, "Going to sleep\n"), (2.0, "Operating channel: 22\n"),
                                              (0.1, "Operating PAN ID: 0xBEEF\n")], clock)
        follower = serial_fox.Follower(source, clock)
        clock.advance(5.0)
        for _ in range(4):
            follower.poll()
        self.assertEqual((follower.channel(), follower.pan_id()), (22, 0xBEEF))
        self.assertEqual(follower.pan_ids(), [0xBEEF])

    def test_two_sleeps_give_two_boundaries_and_wake_3_lines(self):
        """A UART bridge port through two sleeps: each Going to sleep line is
        a boundary, the Cycle behind line printed on the way to sleep stays
        with the ending wake, and wake 3's lines answer for wake 3."""
        clock = serial_fox.FakeClock(0.0)
        source = serial_fox.TranscriptSource([
            (10.0, "Going to sleep\n"), (0.1, "Cycle behind by 1.3s, rebooting at once\n"),
            (5.0, "Initializing...\n"), (0.1, "Last cycle: 16.4s, target 15s\n"), (0.1, "Operating channel: 9\n"),
            (0.1, "Operating PAN ID: 0xBEEF\n"), (0.1, "Awake and screaming\n"),
            (10.0, "Going to sleep\n"),
            (5.0, "Initializing...\n"), (0.1, "Last cycle: 15.5s, target 15s\n"), (0.1, "Operating channel: 4\n"),
            (0.1, "Operating PAN ID: 0xCAFE\n")], clock)
        follower = serial_fox.Follower(source, clock)
        clock.advance(10.05)
        follower.poll()
        self.assertEqual(follower.boundaries(), [10.05])
        clock.advance(0.1)
        follower.poll()
        self.assertEqual(follower.boundaries(), [10.05])
        self.assertEqual(follower.wakes, [])
        clock.advance(5.5)
        for _ in range(6):
            follower.poll()
        self.assertEqual(follower.boundaries(), [10.05])
        self.assertEqual(len(follower.wakes), 1)
        self.assertEqual(follower.channel(2), 9)
        self.assertIsNone(follower.channel(3))
        self.assertEqual(follower.last_cycle(2), 16.4)
        clock.advance(10.0)
        follower.poll()
        self.assertEqual(follower.boundaries(), [10.05, 25.65])
        self.assertAlmostEqual(follower.boundary(), 10.05)
        clock.advance(5.5)
        for _ in range(5):
            follower.poll()
        self.assertEqual(len(follower.wakes), 2)
        self.assertEqual(follower.channel(3), 4)
        self.assertEqual(follower.channel(2), 9)
        self.assertEqual(follower.pan_ids(), [0xBEEF, 0xCAFE])
        self.assertEqual(follower.last_cycle(3), 15.5)
        self.assertIsNone(follower.last_cycle(4))
        self.assertEqual(follower.wake2.integer("channel"), 9)

    def test_native_usb_port_vanishing_twice_with_reopens(self):
        """A native USB board through two sleeps: the port vanishes at each
        sleep, once per wake even after the sleep line, and comes back for the
        next wake's lines."""
        clock = serial_fox.FakeClock(0.0)
        items = [(26.0, "Initializing...\n"), (0.1, "Last cycle: 20.3s, target 20s\n"), (0.1, "Operating channel: 9\n"),
                 (0.1, "Going to sleep\n"), (40.0, "Operating channel: 4\n")]
        source = Vanishing(items, clock, gone_at=20.0, away=5.0)
        follower = serial_fox.Follower(source, clock, reopen=True)
        clock.advance(20.5)
        follower.poll()
        self.assertEqual(follower.boundaries(), [20.5])
        clock.advance(6.0)
        for _ in range(6):
            follower.poll()
        self.assertEqual(follower.channel(2), 9)
        self.assertEqual(follower.last_cycle(2), 20.3)
        self.assertEqual(follower.boundaries(), [20.5, 26.5])
        # The port vanishes again after the sleep line: no third boundary.
        source.vanished = False
        source.gone_at = 27.0
        source.back_at = 30.0
        clock.advance(1.0)
        follower.poll()
        self.assertTrue(follower.gone)
        self.assertEqual(follower.boundaries(), [20.5, 26.5])
        clock.advance(40.0)
        for _ in range(3):
            follower.poll()
        self.assertEqual(source.reopens, 2)
        self.assertEqual(follower.channel(3), 4)


class TranscriptSourceTest(unittest.TestCase):
    def test_elapsed_clock_time_counts_against_the_next_delay(self):
        clock = serial_fox.FakeClock(0.0)
        source = serial_fox.TranscriptSource([(3.0, "late\n")], clock)
        self.assertIsNone(source.read(0.0))
        clock.advance(2.0)
        self.assertIsNone(source.read(0.0))
        clock.advance(1.0)
        self.assertEqual(source.read(0.0), "late\n")
        self.assertEqual(clock.now, 3.0)

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
    """Records the order of line-state changes the way a port would see them,
    with the fake clock's time of each when one is given."""

    instances = []
    clock = None

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
        # Raise on the RTS write once this many events were recorded.
        self.fail_rts_after = None
        # Every event with the fake clock's time, when one is set.
        self.timed = []
        FakeSerial.instances.append(self)

    def _record(self, event):
        self.events.append(event)
        if FakeSerial.clock is not None:
            self.timed.append((FakeSerial.clock(),) + event)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self._dtr = value
        self._record(("dtr", value))

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        if self.fail_rts_after is not None and len(self.events) >= self.fail_rts_after:
            raise OSError(5, "Input/output error")
        self._rts = value
        self._record(("rts", value))

    def open(self):
        self.opened = True
        self._record(("open",))

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


def line_states(events, dtr=None, rts=None):
    """The (DTR, RTS) pairs a port passes through for a list of writes, from
    the given starting state."""
    states = []
    for event in events:
        if event[0] == "dtr":
            dtr = event[1]
        elif event[0] == "rts":
            rts = event[1]
        else:
            continue
        states.append((dtr, rts))
    return states


BRIDGE = devices.Port("/dev/ttyUSB0", *CP210X)
JTAG = devices.Port("/dev/ttyACM0", *ESP)
NANO_PORT = devices.Port("/dev/ttyACM1", *NANO)
# The hard resets as the fake port records them: esptool's RTS pulse with the
# DTR rewrite for the USB-Serial-JTAG peripheral, the bridge pulse ending with
# both lines asserted again.
USB_HARD_RESET = [("rts", True), ("dtr", False), ("rts", False), ("dtr", False)]
BRIDGE_HARD_RESET = [("dtr", False), ("rts", True), ("rts", False), ("dtr", True), ("rts", True)]


class SerialSourceTest(unittest.TestCase):
    """The port is opened and reset with the sequences of its USB stack."""

    def setUp(self):
        FakeSerial.instances = []
        FakeSerial.clock = None
        patcher = mock.patch("serial.Serial", FakeSerial)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.slept = []

    def source(self, port=BRIDGE, sleep=None):
        return serial_fox.SerialSource(port.device, sleep=sleep or self.slept.append, port=port)

    def timed_source(self, port):
        """A source whose sleeps move a fake clock that stamps every write."""
        clock = serial_fox.FakeClock(0.0)
        FakeSerial.clock = clock

        def sleep(seconds):
            self.slept.append(seconds)
            clock.advance(seconds)

        return self.source(port, sleep), clock

    def test_bridge_open_asserts_dtr_then_rts_before_opening(self):
        source = self.source()
        port = FakeSerial.instances[0]
        self.assertEqual(port.port, "/dev/ttyUSB0")
        self.assertEqual(port.baudrate, 115200)
        self.assertEqual(port.events, [("dtr", True), ("rts", True), ("open",)])
        self.assertIs(source.serial, port)
        self.assertEqual(source.stack, usbstack.UART_BRIDGE)

    def test_bridge_reset_is_esptool_hard_reset_then_lines_asserted_again(self):
        source, clock = self.timed_source(BRIDGE)
        port = FakeSerial.instances[0]
        del port.events[:]
        released = source.reset(clock)
        self.assertEqual(port.events, BRIDGE_HARD_RESET)
        self.assertEqual(self.slept, [usbstack.RESET_PULSE_SECONDS, usbstack.RESET_PULSE_SECONDS])
        # Stamped when EN rises, after the first pulse and before the second.
        self.assertEqual(released, usbstack.RESET_PULSE_SECONDS)
        self.assertEqual(clock.now, 2 * usbstack.RESET_PULSE_SECONDS)

    def test_bridge_reset_survives_the_device_dropping_off_the_bus(self):
        source = self.source()
        port = FakeSerial.instances[0]
        port.events = [("start",)]
        port.fail_rts_after = 2
        self.assertIsNotNone(source.reset())
        self.assertEqual(port.events, [("start",), ("dtr", False)])
        self.assertTrue(port.closed)
        self.assertIsNone(source.serial)

    def test_usb_serial_jtag_open_never_asserts_rts_and_ends_with_both_lines_released(self):
        source = self.source(JTAG)
        port = FakeSerial.instances[0]
        self.assertEqual(source.stack, usbstack.USB_SERIAL_JTAG)
        self.assertEqual(port.events, [("dtr", True), ("rts", False), ("open",), ("dtr", False)])
        self.assertNotIn(("rts", True), port.events)
        # RTS is released before DTR, so the lines never pass through RTS
        # asserted alone, the peripheral's reset.
        self.assertNotIn((False, True), line_states(port.events, dtr=True, rts=True))
        self.assertEqual((port.dtr, port.rts), (False, False))

    def test_usb_serial_jtag_reset_is_esptool_s_usb_hard_reset(self):
        source, clock = self.timed_source(JTAG)
        port = FakeSerial.instances[0]
        del port.events[:]
        released = source.reset(clock)
        self.assertEqual(port.events, USB_HARD_RESET)
        self.assertEqual(self.slept, [usbstack.USB_HOLD_SECONDS, usbstack.USB_SETTLE_SECONDS])
        # DTR stays released throughout and RTS is never released while DTR
        # is asserted.
        self.assertEqual([value for name, value in port.events if name == "dtr"], [False, False])
        self.assertNotIn((True, False), line_states(port.events, dtr=False, rts=False))
        # Stamped when RTS is released, 0.2 s in, before the 0.2 s settle.
        self.assertEqual(released, usbstack.USB_HOLD_SECONDS)
        self.assertEqual(clock.now, usbstack.USB_HOLD_SECONDS + usbstack.USB_SETTLE_SECONDS)
        self.assertEqual(port.timed[-2][0], usbstack.USB_HOLD_SECONDS)
        self.assertEqual((port.dtr, port.rts), (False, False))

    def test_usb_serial_jtag_dropping_off_the_bus_during_the_hold_goes_to_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "ttyACM0")
            with open(path, "w"):
                pass
            source, clock = self.timed_source(devices.Port(path, *ESP))
            port = FakeSerial.instances[0]
            del port.events[:]
            port.fail_rts_after = 2
            released = source.reset(clock)
            self.assertEqual(port.events, [("rts", True), ("dtr", False)])
            self.assertEqual(self.slept, [usbstack.USB_HOLD_SECONDS])
            # The chip restarted when reset was asserted, which is the stamp.
            self.assertEqual(released, 0.0)
            self.assertTrue(port.closed)
            self.assertIsNone(source.serial)
            with self.assertRaises(serial_fox.PortGone):
                source.read(0.0)
            source.reopen(Deadline(1.0, clock))
            self.assertEqual(len(FakeSerial.instances), 2)
            self.assertEqual(FakeSerial.instances[-1].events, [("dtr", True), ("rts", False), ("open",), ("dtr", False)])

    def test_usb_serial_jtag_gone_before_the_first_write_is_port_gone_too(self):
        source = self.source(JTAG)
        port = FakeSerial.instances[0]
        del port.events[:]
        port.fail_rts_after = 0
        self.assertIsNotNone(source.reset())
        self.assertEqual(port.events, [])
        self.assertIsNone(source.serial)

    def test_nano_is_opened_with_both_lines_asserted_and_never_reset(self):
        source = self.source(NANO_PORT)
        port = FakeSerial.instances[0]
        self.assertEqual(source.stack, usbstack.TINYUSB)
        self.assertEqual(port.events, [("dtr", True), ("rts", True), ("open",)])
        del port.events[:]
        self.assertIsNone(source.reset())
        self.assertEqual(port.events, [])
        self.assertEqual(self.slept, [])
        self.assertIs(source.serial, port)

    def test_unknown_id_and_no_id_get_the_bridge_sequences(self):
        for port in (devices.Port("/dev/ttyUSB1", *OTHER), devices.Port("/dev/ttyS0", None, None, None, None), None):
            FakeSerial.instances = []
            self.slept = []
            path = port.device if port is not None else "/dev/ttyS1"
            with mock.patch.object(devices, "list_ports", return_value=[]):
                source = serial_fox.SerialSource(path, sleep=self.slept.append, port=port)
            fake = FakeSerial.instances[0]
            self.assertIsNone(source.stack, port)
            self.assertEqual(fake.events, [("dtr", True), ("rts", True), ("open",)], port)
            del fake.events[:]
            source.reset()
            self.assertEqual(fake.events, BRIDGE_HARD_RESET, port)

    def test_port_is_looked_up_by_path_when_not_given(self):
        listed = [devices.Port("/dev/ttyUSB0", *CP210X), devices.Port("/dev/ttyACM0", *ESP)]
        with mock.patch.object(devices, "list_ports", return_value=listed):
            source = serial_fox.SerialSource("/dev/ttyACM0", sleep=self.slept.append)
        self.assertEqual(source.port, listed[1])
        self.assertEqual(source.stack, usbstack.USB_SERIAL_JTAG)
        self.assertEqual(FakeSerial.instances[0].events, [("dtr", True), ("rts", False), ("open",), ("dtr", False)])

    def test_release_and_reset_write_the_same_lines_for_the_same_stack(self):
        from foxverify import bootloader
        for port, expected in ((BRIDGE, BRIDGE_HARD_RESET), (JTAG, USB_HARD_RESET)):
            FakeSerial.instances = []
            said = []
            bootloader.release(bootloader.Hold(True, port.device, port), said.append, self.slept.append)
            released = FakeSerial.instances[0]
            self.assertEqual(said, [bootloader.RELEASED % port.device])
            self.assertTrue(released.closed)
            FakeSerial.instances = []
            source = self.source(port)
            source.reset()
            reset = FakeSerial.instances[0]
            self.assertEqual(released.events, reset.events, port)
            self.assertEqual(released.events[-len(expected):], expected, port)

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
            source = serial_fox.SerialSource(path, sleep=clock.advance, port=devices.Port(path, *CP210X))
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


class DownloadModeTest(unittest.TestCase):
    """The ROM's download-mode lines, as the boards print them."""

    def test_rom_lines(self):
        self.assertEqual(serial_fox.download_mode_line(
            "rst:0x1 (POWERON),boot:0x0 (DOWNLOAD(USB/UART0))\r"), serial_fox.BOOT_LINE)
        self.assertEqual(serial_fox.download_mode_line(
            "rst:0x15 (USB_UART_CHIP_RESET),boot:0x0 (DOWNLOAD(USB/UART0))"), serial_fox.BOOT_LINE)
        self.assertEqual(serial_fox.download_mode_line(
            "rst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))"), serial_fox.BOOT_LINE)
        self.assertEqual(serial_fox.download_mode_line("waiting for download\r"), serial_fox.WAITING_LINE)
        for line in ("rst:0x1 (POWERON),boot:0xc (SPI_FAST_FLASH_BOOT)", "rst:0x1 (POWERON),boot:0x8 (SPI_FAST_FLASH_BOOT)",
                     "rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)", "Initializing...",
                     "Fox: iBeacon EASY", "entry 0x4084bb20"):
            self.assertIsNone(serial_fox.download_mode_line(line), line)
        for name in TRANSCRIPTS:
            for line in transcript(name).splitlines():
                self.assertIsNone(serial_fox.download_mode_line(line), (name, line))


if __name__ == "__main__":
    unittest.main()
