import io
import os
import shutil
import struct
import subprocess
import tempfile
import unittest

from foxverify import conf, report, tshark, zigbee
from foxverify.report import RunError
from foxverify.serial_fox import parse_transcript
from foxverify.tests import frozen_text, read_fixture
from foxverify.tests.fakes import FakeReader, deadline

HEADER = frozen_text("zigbee_coordinator")
FRAMES = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
RECEIVED = read_fixture("sniffer", "received.log").splitlines()

# A Link Status from the demo EASY coordinator, as the sniffer reports it:
# 802.15.4 data frame to the broadcast address of PAN 0x1337 from short
# address 0x0000, Zigbee NWK command to 0xFFFC with the extended source
# F2:5A:3C:91:0E:7B:44:D8, command id 0x08 with first and last frame set.
LINK_STATUS_HEX = "41882a3713ffff00000910fcff00000105d8447b0e913c5af20860"
MAC = "F2:5A:3C:91:0E:7B:44:D8"


def frame(index):
    return zigbee.parse_frame(tshark.parse_line(FRAMES[index], zigbee.FIELDS))


class ReceivedLineTest(unittest.TestCase):
    def test_parse_received(self):
        captured = zigbee.parse_received(RECEIVED[1])
        self.assertEqual(captured.frame.hex(), LINK_STATUS_HEX)
        self.assertEqual(captured.power, -45)
        self.assertEqual(captured.lqi, 200)
        self.assertEqual(captured.time, 123456)

    def test_extra_spaces_and_negative_time(self):
        captured = zigbee.parse_received(RECEIVED[2])
        self.assertEqual(captured.frame, bytes.fromhex("03083affffffff07"))
        self.assertEqual(captured.power, -70)
        captured = zigbee.parse_received(RECEIVED[4])
        self.assertEqual(captured.time, -5)

    def test_other_lines_are_ignored(self):
        self.assertIsNone(zigbee.parse_received(RECEIVED[0]))
        self.assertIsNone(zigbee.parse_received(RECEIVED[3]))
        self.assertIsNone(zigbee.parse_received("received: abc power: 1 lqi: 1 time: 1"))

    def test_commands_end_in_crlf(self):
        self.assertEqual(zigbee.command_line("channel 15"), b"channel 15\r\n")
        self.assertEqual(zigbee.command_line("receive"), b"receive\r\n")
        self.assertEqual(zigbee.command_line("sleep"), b"sleep\r\n")


class PcapTest(unittest.TestCase):
    def test_global_header(self):
        header = zigbee.pcap_global_header()
        self.assertEqual(len(header), 24)
        magic, major, minor, zone, sigfigs, snaplen, network = struct.unpack("<IHHiIII", header)
        self.assertEqual((magic, major, minor, zone, sigfigs, snaplen, network),
                         (0xA1B2C3D4, 2, 4, 0, 0, 255, 283))

    def test_record_matches_a_hand_built_one(self):
        captured = zigbee.parse_received(RECEIVED[1])
        record = zigbee.pcap_record(captured, 15, 1730000010.5)
        frame_bytes = bytes.fromhex(LINK_STATUS_HEX)
        tap = (b"\x00\x00\x1c\x00"
               + b"\x01\x00\x04\x00" + struct.pack("<f", -45.0)
               + b"\x03\x00\x03\x00" + b"\x0f\x00" + b"\x00\x00"
               + b"\x0a\x00\x01\x00" + b"\xc8\x00\x00\x00")
        self.assertEqual(len(tap), 28)
        expected = struct.pack("<IIII", 1730000010, 500000, 28 + len(frame_bytes), 28 + len(frame_bytes)) + tap + frame_bytes
        self.assertEqual(record, expected)

    def test_timestamp_rounding_carries_into_seconds(self):
        captured = zigbee.Captured(b"\x01", 0, 0, 0)
        record = zigbee.pcap_record(captured, 11, 1730000010.9999999)
        seconds, micros = struct.unpack("<II", record[:8])
        self.assertEqual((seconds, micros), (1730000011, 0))


class FakePort:
    def __init__(self, lines):
        self.lines = list(lines)
        self.written = []
        self.closed = False

    def write(self, data):
        self.written.append(data)

    def readline(self):
        if self.lines:
            return self.lines.pop(0).encode("ascii") + b"\r\n"
        return b""

    def close(self):
        self.closed = True


class PumpTest(unittest.TestCase):
    def test_pump_writes_records_and_sleeps_on_stop(self):
        port = FakePort(RECEIVED)
        sink = io.BytesIO()
        times = iter([1730000010.5, 1730000011.0, 1730000012.0])
        pump = zigbee.Pump(port, sink, 15, clock=lambda: next(times))
        pump.start()
        for _ in range(100):
            if pump.frames == 3:
                break
            pump.join(0.05)
        pump.stop()
        self.assertEqual(port.written, [b"channel 15\r\n", b"receive\r\n", b"sleep\r\n"])
        self.assertEqual(pump.frames, 3)
        self.assertIsNone(pump.error)
        data = sink.getvalue()
        self.assertEqual(data[:len(zigbee.pcap_record(zigbee.parse_received(RECEIVED[1]), 15, 1730000010.5))],
                         zigbee.pcap_record(zigbee.parse_received(RECEIVED[1]), 15, 1730000010.5))


class FrameTest(unittest.TestCase):
    def test_link_status_in_the_clear(self):
        f = frame(2)
        self.assertTrue(f.from_coordinator())
        self.assertTrue(f.is_link_status())
        self.assertEqual(f.pan, 0x1337)
        self.assertEqual(f.channel, 15)
        self.assertEqual(f.short, 0)
        self.assertEqual(f.mac, MAC)
        self.assertEqual(f.command, 0x08)
        self.assertAlmostEqual(f.time, 1730000010.5)

    def test_encrypted_link_status_identified_by_shape(self):
        f = frame(4)
        self.assertIsNone(f.command)
        self.assertTrue(f.is_link_status())
        self.assertEqual(f.mac, MAC)

    def test_other_frames(self):
        beacon_like = frame(0)
        self.assertTrue(beacon_like.from_coordinator())
        self.assertFalse(beacon_like.is_link_status())
        self.assertEqual(beacon_like.mac, MAC)
        self.assertEqual(beacon_like.pan, 0x1337)
        other = frame(1)
        self.assertFalse(other.from_coordinator())

    def test_interval_fits(self):
        self.assertIsNone(zigbee.interval_fits(1, 10))
        self.assertIsNone(zigbee.interval_fits(15, 32))
        self.assertEqual(zigbee.interval_fits(15, 31.5), "two Link Status frames need up to 32 s, 32 s left")
        self.assertEqual(zigbee.interval_fits(30, 50), "two Link Status frames need up to 62 s, 50 s left")

    def test_collect_stops_after_two_link_status_frames(self):
        dl, clock = deadline(60)
        reader = FakeReader(zigbee.FIELDS, [(0.5, line) for line in FRAMES], clock)
        observation = zigbee.collect(reader, dl, 0x1337, 2)
        self.assertEqual(len(observation.frames), 3)
        self.assertEqual(len(observation.link_status), 2)
        self.assertAlmostEqual(observation.gap(), 1.0)
        self.assertEqual(observation.first().command, 0x08)
        self.assertEqual(clock.now, 1002.0)

    def test_collect_ignores_other_pans_for_the_interval(self):
        dl, clock = deadline(5)
        reader = FakeReader(zigbee.FIELDS, [(0.5, line) for line in FRAMES], clock)
        observation = zigbee.collect(reader, dl, 0xBEEF, 2)
        self.assertEqual(len(observation.frames), 4)
        self.assertEqual(observation.link_status, [])
        self.assertEqual(observation.first().pan, 0x1337)
        self.assertIsNone(observation.gap())
        self.assertTrue(dl.expired())

    def test_collect_raises_when_tshark_exits(self):
        dl, clock = deadline(5)
        reader = FakeReader(zigbee.FIELDS, [(0.5, None)], clock)
        with self.assertRaises(RunError):
            zigbee.collect(reader, dl, None, 1)


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.block = conf.select(HEADER, ["COORDINATOR", "EASY"])
        self.readback = parse_transcript(read_fixture("transcripts", "zigbee_easy.log"))

    def rows(self):
        return {row.value: row for row in self.report.rows}

    def test_all_pass(self):
        observation = zigbee.Observation([frame(2), frame(3)], [frame(2), frame(3)])
        zigbee.rows(self.report, self.block, self.readback, observation)
        rows = self.rows()
        self.assertEqual([row.verdict for row in self.report.rows], ["pass"] * 5)
        self.assertEqual(rows["PAN_ID"].air, "0x1337")
        self.assertEqual(rows["SHORT_ADDR"].air, "0x0000")
        self.assertEqual(rows["PACKET_INTERVAL"].air, "1.0 s between Link Status frames")
        self.assertEqual(rows["MAC_ADDR"].air, MAC)

    def test_interval_outside_tolerance_fails(self):
        late = frame(3)._replace(time=frame(2).time + 2.5)
        zigbee.rows(self.report, self.block, self.readback, zigbee.Observation([frame(2), late], [frame(2), late]))
        self.assertEqual(self.rows()["PACKET_INTERVAL"].verdict, "FAIL")

    def test_interval_budget_reason(self):
        observation = zigbee.Observation([frame(2)], [frame(2)])
        zigbee.rows(self.report, self.block, self.readback, observation,
                    interval_reason="two Link Status frames need up to 32 s, 20 s left")
        row = self.rows()["PACKET_INTERVAL"]
        self.assertEqual(row.verdict, "unverified")
        self.assertEqual(row.reason, "two Link Status frames need up to 32 s, 20 s left")
        self.assertEqual(self.rows()["MAC_ADDR"].verdict, "pass")

    def test_one_link_status_only(self):
        zigbee.rows(self.report, self.block, self.readback, zigbee.Observation([frame(2)], [frame(2)]))
        row = self.rows()["PACKET_INTERVAL"]
        self.assertEqual(row.verdict, "unverified")
        self.assertEqual(row.reason, "1 Link Status frame heard, two needed")

    def test_nothing_heard(self):
        zigbee.rows(self.report, self.block, self.readback, None, reason="no sniffer")
        self.assertEqual([row.verdict for row in self.report.rows], ["unverified"] * 5)
        self.assertEqual(self.report.rows[0].reason, "no sniffer")

    def test_random_pan_and_channel_accept_the_fox_values(self):
        text = HEADER.replace("#define CHANNEL 15", "#define CHANNEL 0").replace("#define PAN_ID 0x1337", "#define PAN_ID 0")
        block = conf.select(text, ["COORDINATOR", "EASY"])
        zigbee.rows(self.report, block, self.readback, zigbee.Observation([frame(2), frame(3)], [frame(2), frame(3)]))
        rows = self.rows()
        self.assertEqual((rows["CHANNEL"].header, rows["CHANNEL"].verdict), ("random", "pass"))
        self.assertEqual((rows["PAN_ID"].header, rows["PAN_ID"].serial, rows["PAN_ID"].verdict), ("random", "0x1337", "pass"))

    def test_wrong_pan_on_air_fails(self):
        wrong = frame(2)._replace(pan=0xBEEF)
        zigbee.rows(self.report, self.block, self.readback, zigbee.Observation([wrong], []))
        self.assertEqual(self.rows()["PAN_ID"].verdict, "FAIL")
        self.assertEqual(self.rows()["PAN_ID"].air, "0xBEEF")


@unittest.skipIf(shutil.which("tshark") is None, "tshark is not installed; the pcap decode test needs it")
class TsharkDecodeTest(unittest.TestCase):
    """tshark reads a pcap the writer produced and decodes the Link Status."""

    def test_decode(self):
        workdir = tempfile.mkdtemp(prefix="foxverify-pcap-")
        self.addCleanup(shutil.rmtree, workdir)
        path = os.path.join(workdir, "link_status.pcap")
        captured = zigbee.parse_received(RECEIVED[1])
        with open(path, "wb") as handle:
            handle.write(zigbee.pcap_global_header())
            handle.write(zigbee.pcap_record(captured, 15, 1730000010.5))
            handle.write(zigbee.pcap_record(captured, 15, 1730000011.5))
        argv = tshark.file_command(shutil.which("tshark"), path, zigbee.FIELDS)
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2, result.stdout)
        frames = [zigbee.parse_frame(tshark.parse_line(line, zigbee.FIELDS)) for line in lines]
        first = frames[0]
        self.assertEqual(first.pan, 0x1337)
        self.assertEqual(first.short, 0x0000)
        self.assertEqual(first.channel, 15)
        self.assertEqual(first.command, zigbee.LINK_STATUS)
        self.assertEqual(first.mac, MAC)
        self.assertTrue(first.is_link_status())
        self.assertAlmostEqual(frames[1].time - first.time, 1.0)
        record = tshark.parse_line(lines[0], zigbee.FIELDS)
        self.assertEqual(record.get("wpan.src16"), "0x0000")
        self.assertEqual(record.get("wpan-tap.ch_num"), "15")
        self.assertEqual(record.get("zbee_nwk.cmd.id"), "0x08")
        # With PAN ID compression the frame carries one PAN ID, which
        # Wireshark files under the destination; the source PAN is the same.
        self.assertIn("0x1337", (record.get("wpan.src_pan"), record.get("wpan.dst_pan")))

    def test_observe_through_the_fifo(self):
        """The whole path: a fake sniffer port, the pump thread, the FIFO,
        tshark and the Link Status gap."""
        import time

        class TimedPort(FakePort):
            def __init__(self, items):
                FakePort.__init__(self, [])
                self.items = list(items)

            def readline(self):
                if not self.items:
                    time.sleep(0.05)
                    return b""
                delay, line = self.items.pop(0)
                time.sleep(delay)
                return line.encode("ascii") + b"\r\n"

        port = TimedPort([(0.2, RECEIVED[0]), (0.2, RECEIVED[1]), (1.0, RECEIVED[1])])
        dl = report.Deadline(20)
        observation = zigbee.observe("/dev/fake", 15, dl, shutil.which("tshark"), pan_id=0x1337,
                                     open_port=lambda path: port)
        self.assertEqual(len(observation.link_status), 2)
        self.assertEqual(observation.first().mac, MAC)
        self.assertEqual(observation.first().channel, 15)
        self.assertAlmostEqual(observation.gap(), 1.0, delta=0.3)
        self.assertEqual(port.written, [b"channel 15\r\n", b"receive\r\n", b"sleep\r\n"])
        self.assertTrue(port.closed)


if __name__ == "__main__":
    unittest.main()
