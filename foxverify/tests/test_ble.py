import io
import sys
import types
import unittest

from foxverify import ble, conf, report
from foxverify.report import RunError
from foxverify.serial_fox import parse_transcript
from foxverify.tests import frozen_text, read_fixture

HEADER = frozen_text("iBeacon")
# The manufacturer data the demo EASY fox advertises, after the company id.
PAYLOAD = bytes.fromhex("0215" "A2AFA582E4E84599B28B4E11AC6DD6E8" "0005" "0058" "C5")


class DecodeTest(unittest.TestCase):
    def test_payload_after_the_company_id(self):
        beacon = ble.decode_ibeacon(PAYLOAD)
        self.assertEqual(beacon.uuid, "A2AFA582-E4E8-4599-B28B-4E11AC6DD6E8")
        self.assertEqual(beacon.major, 5)
        self.assertEqual(beacon.minor, 88)
        self.assertEqual(beacon.signal_power, -59)

    def test_full_block_with_the_company_id(self):
        beacon = ble.decode_ibeacon(b"\x4c\x00" + PAYLOAD)
        self.assertEqual(beacon.major, 5)
        self.assertEqual(beacon.signal_power, -59)

    def test_positive_signal_power_and_big_endian_fields(self):
        data = bytearray(PAYLOAD)
        data[18:20] = b"\x12\x34"
        data[20:22] = b"\xab\xcd"
        data[22] = 0x7F
        beacon = ble.decode_ibeacon(bytes(data))
        self.assertEqual((beacon.major, beacon.minor, beacon.signal_power), (0x1234, 0xABCD, 127))

    def test_not_an_ibeacon(self):
        self.assertIsNone(ble.decode_ibeacon(b""))
        self.assertIsNone(ble.decode_ibeacon(PAYLOAD[:-1]))
        self.assertIsNone(ble.decode_ibeacon(b"\x01" + PAYLOAD[1:]))
        self.assertIsNone(ble.decode_ibeacon(b"\x02\x14" + PAYLOAD[2:]))

    def test_name_rule(self):
        name = "Demo Bruce BLE Easy Fox"
        self.assertEqual(ble.expected_name(name), name)
        exactly = "A" * 29
        self.assertEqual(ble.expected_name(exactly), exactly)
        self.assertEqual(ble.expected_name("B" * 30), "B" * 29)
        self.assertEqual(ble.NAME_LIMIT, 29)

    def test_device_path(self):
        self.assertEqual(ble.device_path("hci0", "f2:82:42:d0:84:bc"), "/org/bluez/hci0/dev_F2_82_42_D0_84_BC")

    def test_merge_keeps_what_the_other_packet_brought(self):
        seen = ble.merge(None, "f2:82:42:d0:84:bc", None, PAYLOAD, -50, 1.0)
        self.assertEqual(seen.address, "F2:82:42:D0:84:BC")
        self.assertIsNone(seen.name)
        self.assertFalse(seen.complete())
        seen = ble.merge(seen, "F2:82:42:D0:84:BC", "Demo Bruce BLE Easy Fox", None, None, 2.0)
        self.assertTrue(seen.complete())
        self.assertEqual(seen.beacon.minor, 88)
        self.assertEqual(seen.rssi, -50)
        self.assertEqual(seen.time, 2.0)


class MissingBleakTest(unittest.TestCase):
    def test_message_names_packages_and_the_venv(self):
        saved = sys.modules.get("bleak")
        sys.modules["bleak"] = None
        try:
            with self.assertRaises(RunError) as caught:
                ble.import_bleak()
        finally:
            if saved is None:
                del sys.modules["bleak"]
            else:
                sys.modules["bleak"] = saved
        text = str(caught.exception)
        self.assertEqual(text, ble.BLEAK_MISSING)
        self.assertIn("python3-bleak", text)
        self.assertIn("python-bleak", text)
        self.assertIn("GURU", text)
        self.assertIn("python3 -m venv --system-site-packages .venv && .venv/bin/pip install bleak", text)

    def test_scan_thread_fails_before_starting(self):
        saved = sys.modules.get("bleak")
        sys.modules["bleak"] = None
        try:
            scan = ble.BleScan("hci0", "F2:82:42:D0:84:BC", report.Deadline(1))
            with self.assertRaises(RunError):
                scan.start()
            self.assertFalse(scan.is_alive())
        finally:
            if saved is None:
                del sys.modules["bleak"]
            else:
                sys.modules["bleak"] = saved


class FakeAdvertisement:
    def __init__(self, local_name=None, payload=None, rssi=-50):
        self.local_name = local_name
        self.manufacturer_data = {} if payload is None else {ble.APPLE_COMPANY_ID: payload}
        self.rssi = rssi


class FakeDevice:
    def __init__(self, address):
        self.address = address


class FakeBleak(types.ModuleType):
    """A bleak whose scanner delivers a scripted list of (device, advertisement)
    pairs, one every few milliseconds, then repeats the last one."""

    script = []
    started = []

    def __init__(self):
        types.ModuleType.__init__(self, "bleak")
        module = self

        class BleakScanner:
            def __init__(self, detection_callback, adapter, scanning_mode):
                self.callback = detection_callback
                module.started.append((adapter, scanning_mode))
                self.task = None

            async def start(self):
                import asyncio

                async def deliver():
                    for device, advertisement in module.script:
                        await asyncio.sleep(0.01)
                        self.callback(device, advertisement)

                self.task = asyncio.ensure_future(deliver())

            async def stop(self):
                self.task.cancel()

        self.BleakScanner = BleakScanner


class ScanTest(unittest.TestCase):
    """scan_async and BleScan against the fake bleak: every candidate address is
    collected, the late target ends the scan, and the rest is ignored."""

    FOX = "F2:82:42:D0:84:BC"
    OTHER_FOX = "F2:63:89:10:8D:1D"

    def setUp(self):
        self.bleak = FakeBleak()
        self.bleak.script = [
            (FakeDevice("AA:BB:CC:DD:EE:FF"), FakeAdvertisement("Someone's phone")),
            (FakeDevice(self.OTHER_FOX.lower()), FakeAdvertisement(None, PAYLOAD)),
            (FakeDevice(self.FOX), FakeAdvertisement(None, PAYLOAD)),
            (FakeDevice(self.FOX), FakeAdvertisement("Demo Bruce BLE Easy Fox", None)),
            (FakeDevice(self.OTHER_FOX), FakeAdvertisement("Demo Cath BLE Medium Fox", None)),
        ]
        self.bleak.started = []
        saved = sys.modules.get("bleak")
        sys.modules["bleak"] = self.bleak

        def restore():
            if saved is None:
                sys.modules.pop("bleak", None)
            else:
                sys.modules["bleak"] = saved

        self.addCleanup(restore)

    def test_scan_collects_candidates_until_the_target_is_complete(self):
        import asyncio
        deadline = report.Deadline(5)
        seen = asyncio.run(ble.scan_async("hci1", [self.FOX, self.OTHER_FOX], deadline, remove_cached=False,
                                          target=lambda: self.FOX))
        self.assertEqual(self.bleak.started, [("hci1", "active")])
        self.assertEqual(set(seen), {self.FOX, self.OTHER_FOX})
        self.assertTrue(seen[self.FOX].complete())
        self.assertEqual(seen[self.FOX].name, "Demo Bruce BLE Easy Fox")
        self.assertEqual(seen[self.FOX].beacon.minor, 88)
        self.assertFalse(seen[self.OTHER_FOX].complete())
        self.assertLess(deadline.elapsed(), 2.0)

    def test_scan_without_a_target_runs_to_the_deadline(self):
        import asyncio
        deadline = report.Deadline(0.6)
        seen = asyncio.run(ble.scan_async("hci0", self.FOX, deadline, remove_cached=False))
        self.assertTrue(deadline.expired())
        self.assertEqual(list(seen), [self.FOX])
        self.assertTrue(seen[self.FOX].complete())

    def test_thread_takes_the_target_late(self):
        import time
        scan = ble.BleScan("hci0", [self.FOX, self.OTHER_FOX], report.Deadline(5), remove_cached=False)
        scan.start()
        time.sleep(0.2)
        self.assertTrue(scan.is_alive())
        scan.set_target(self.OTHER_FOX.lower())
        seen = scan.result()
        self.assertFalse(scan.is_alive())
        self.assertTrue(seen[self.OTHER_FOX].complete())
        self.assertEqual(seen[self.OTHER_FOX].name, "Demo Cath BLE Medium Fox")
        self.assertEqual(ble.address_set("f2:82:42:d0:84:bc"), frozenset([self.FOX]))
        self.assertTrue(ble.target_complete(seen, self.FOX))
        self.assertFalse(ble.target_complete(seen, None))
        self.assertFalse(ble.target_complete(seen, "00:11:22:33:44:55"))

    def test_thread_stop(self):
        scan = ble.BleScan("hci0", self.FOX, report.Deadline(5), remove_cached=False)
        self.bleak.script = []
        scan.start()
        scan.stop()
        seen = scan.result(report.Deadline(2))
        self.assertEqual(seen, {})

    def test_every_packet_is_logged_with_its_rssi_and_time(self):
        import time
        times = iter([10.0, 11.0, 12.0, 13.0, 14.0])
        scan = ble.BleScan("hci0", [self.FOX, self.OTHER_FOX], report.Deadline(5), remove_cached=False,
                           clock=lambda: next(times))
        scan.start()
        time.sleep(0.2)
        scan.set_target(self.FOX)
        scan.result()
        # The clock is read for candidate addresses only: the phone's packet
        # takes no time, the other fox's takes 10.0, the fox's 11.0 and 12.0.
        self.assertEqual(scan.take_heard(self.FOX), [ble.Heard(11.0, -50), ble.Heard(12.0, -50)])
        self.assertEqual(scan.take_heard(self.FOX), [])
        self.assertEqual(scan.take_heard(self.OTHER_FOX.lower())[0], ble.Heard(10.0, -50))
        self.assertTrue(scan.complete(self.FOX))
        self.assertFalse(scan.complete("00:11:22:33:44:55"))

    def test_keep_scanning_runs_past_the_complete_target(self):
        import time
        scan = ble.BleScan("hci0", self.FOX, report.Deadline(5), remove_cached=False)
        scan.keep_scanning = True
        scan.set_target(self.FOX)
        scan.start()
        time.sleep(0.4)
        self.assertTrue(scan.complete(self.FOX))
        self.assertTrue(scan.is_alive())
        scan.keep_scanning = False
        seen = scan.result(report.Deadline(2))
        self.assertFalse(scan.is_alive())
        self.assertTrue(seen[self.FOX].complete())


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.block = conf.select(HEADER, ["EASY"])
        self.readback = parse_transcript(read_fixture("transcripts", "ibeacon_easy.log"))

    def rows(self):
        return {row.value: row for row in self.report.rows}

    def test_all_pass(self):
        seen = ble.Seen("F2:82:42:D0:84:BC", "Demo Bruce BLE Easy Fox", ble.decode_ibeacon(PAYLOAD), -50, 1.0)
        ble.rows(self.report, self.block, self.readback, seen)
        self.assertEqual([row.verdict for row in self.report.rows], ["pass"] * 6)
        rows = self.rows()
        self.assertEqual(rows["SIGNAL_POWER"].header, "-59")
        self.assertEqual(rows["SIGNAL_POWER"].air, "-59")
        self.assertEqual(rows["BEACON_UUID"].air, "A2AFA582-E4E8-4599-B28B-4E11AC6DD6E8")

    def test_payload_without_the_name(self):
        seen = ble.Seen("F2:82:42:D0:84:BC", None, ble.decode_ibeacon(PAYLOAD), -50, 1.0)
        ble.rows(self.report, self.block, self.readback, seen)
        rows = self.rows()
        self.assertEqual(rows["DEVICE_NAME"].verdict, "unverified")
        self.assertEqual(rows["DEVICE_NAME"].reason, "seen without a scan response carrying the name")
        self.assertEqual(rows["MAJOR"].verdict, "pass")

    def test_name_without_the_payload(self):
        seen = ble.Seen("F2:82:42:D0:84:BC", "Demo Bruce BLE Easy Fox", None, -50, 1.0)
        ble.rows(self.report, self.block, self.readback, seen)
        rows = self.rows()
        self.assertEqual(rows["DEVICE_NAME"].verdict, "pass")
        self.assertEqual(rows["MINOR"].verdict, "unverified")
        self.assertEqual(rows["MINOR"].reason, "seen without an iBeacon payload")

    def test_not_seen(self):
        ble.rows(self.report, self.block, self.readback, None)
        self.assertEqual([row.verdict for row in self.report.rows], ["unverified"] * 6)
        self.assertEqual(self.report.rows[0].reason, "not seen by the scan")

    def test_wrong_values_fail(self):
        wrong = ble.decode_ibeacon(PAYLOAD)._replace(minor=89, signal_power=-60)
        seen = ble.Seen("F2:82:42:D0:84:BD", "Other", wrong, -50, 1.0)
        ble.rows(self.report, self.block, self.readback, seen)
        rows = self.rows()
        self.assertEqual(rows["MAC_ADDR"].verdict, "FAIL")
        self.assertEqual(rows["DEVICE_NAME"].verdict, "FAIL")
        self.assertEqual(rows["MINOR"].verdict, "FAIL")
        self.assertEqual(rows["SIGNAL_POWER"].verdict, "FAIL")
        self.assertEqual(rows["MAJOR"].verdict, "pass")


if __name__ == "__main__":
    unittest.main()
