import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from foxverify import devices
from foxverify.report import Deadline, RunError


class Info:
    """What pyserial's comports() yields, reduced to the fields the rules read."""

    def __init__(self, device, vid=None, pid=None, product=None, serial_number=None):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.product = product
        self.serial_number = serial_number


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeTree:
    """A temporary /dev, /dev/serial/by-id, /sys/class/net and /sys/class/bluetooth."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="foxverify-devices-")
        self.dev = os.path.join(self.root, "dev")
        self.by_id = os.path.join(self.dev, "serial", "by-id")
        self.net = os.path.join(self.root, "net")
        self.bluetooth = os.path.join(self.root, "bluetooth")
        for path in (self.dev, self.by_id, self.net, self.bluetooth):
            os.makedirs(path)

    def cleanup(self):
        shutil.rmtree(self.root)

    def port(self, name, vid=None, pid=None, product=None, serial_number=None, link=None):
        path = os.path.join(self.dev, name)
        with open(path, "w"):
            pass
        if link:
            os.symlink(os.path.join("..", "..", name), os.path.join(self.by_id, link))
        return Info(path, vid, pid, product, serial_number)

    def interface(self, name):
        os.makedirs(os.path.join(self.net, name))

    def adapter(self, name):
        os.makedirs(os.path.join(self.bluetooth, name))


ESP = (0x303A, 0x1001, "USB JTAG/serial debug unit", "F4:12:FA:00:11:22")
CP210X = (0x10C4, 0xEA60, "CP2104 USB to UART Bridge Controller", "0123ABCD")
CH9102 = (0x1A86, 0x55D4, "USB Single Serial", "5698001234")
FTDI = (0x0403, 0x6001, "FT232R USB UART", "A50285BI")
NRF = (0x1915, 0x154A, "nRF Sniffer for 802.15.4", "F1D2E3C4B5A6")
OTHER = (0x1234, 0x5678, "Some modem", "X1")


class DevicesTestCase(unittest.TestCase):
    def setUp(self):
        self.tree = FakeTree()
        self.addCleanup(self.tree.cleanup)
        self.clock = Clock()

    def comports(self, *infos):
        return lambda: list(infos)

    def autodetect(self, infos, wait=30, deadline=None, said=None):
        return devices.autodetect_fox(
            wait, deadline, self.comports(*infos), self.clock.sleep, self.clock,
            said.append if said is not None else (lambda text: None), self.tree.by_id)


class ClassifyTest(DevicesTestCase):
    def classify(self, name, infos):
        return devices.classify(name, devices.list_ports(self.comports(*infos)),
                               net_dir=self.tree.net, by_id_dir=self.tree.by_id, dev_dir=self.tree.dev)

    def test_network_interface(self):
        self.tree.interface("wlan1")
        device = self.classify("wlan1", [])
        self.assertEqual(device.kind, devices.WIFI)
        self.assertEqual(device.path, "wlan1")

    def test_bluetooth_adapter(self):
        self.assertEqual(self.classify("hci0", []).kind, devices.HCI)
        self.assertEqual(self.classify("hci12", []).kind, devices.HCI)

    def test_sniffer_by_usb_id(self):
        info = self.tree.port("ttyACM3", *NRF, link="usb-ZEPHYR_nRF_Sniffer_for_802.15.4_F1D2E3C4B5A6-if00")
        device = self.classify(info.device, [info])
        self.assertEqual(device.kind, devices.SNIFFER)
        self.assertEqual(device.path, os.path.join(self.tree.by_id,
                                                   "usb-ZEPHYR_nRF_Sniffer_for_802.15.4_F1D2E3C4B5A6-if00"))

    def test_any_other_serial_port_is_the_fox(self):
        fox = self.tree.port("ttyUSB0", *CP210X, link="usb-Silicon_Labs_CP2104_0123ABCD-if00-port0")
        other = self.tree.port("ttyUSB1", *OTHER)
        device = self.classify(fox.device, [fox, other])
        self.assertEqual(device.kind, devices.FOX)
        self.assertEqual(device.path, os.path.join(self.tree.by_id, "usb-Silicon_Labs_CP2104_0123ABCD-if00-port0"))
        self.assertEqual(self.classify(other.device, [fox, other]).kind, devices.FOX)
        self.assertEqual(self.classify(other.device, [fox, other]).path, other.device)

    def test_bare_device_name_and_by_id_path_resolve_to_the_same_fox(self):
        fox = self.tree.port("ttyACM0", *ESP, link="usb-Espressif_USB_JTAG_serial_debug_unit_F4:12:FA:00:11:22-if00")
        by_name = self.classify("ttyACM0", [fox])
        by_link = self.classify(os.path.join(self.tree.by_id, "usb-Espressif_USB_JTAG_serial_debug_unit_F4:12:FA:00:11:22-if00"), [fox])
        self.assertEqual(by_name.kind, devices.FOX)
        self.assertEqual(by_name.path, by_link.path)
        self.assertEqual(by_name.port, by_link.port)
        self.assertEqual(by_name.port.device, fox.device)

    def test_serial_port_without_usb_info_is_the_fox(self):
        path = os.path.join(self.tree.dev, "ttyS0")
        with open(path, "w"):
            pass
        device = self.classify(path, [])
        self.assertEqual(device.kind, devices.FOX)
        self.assertIsNone(device.port)

    def test_unknown_name_is_a_run_error(self):
        with self.assertRaises(RunError) as caught:
            self.classify("wlan9", [])
        self.assertIn("wlan9", str(caught.exception))
        self.assertEqual(caught.exception.exit_code, 2)
        with self.assertRaises(RunError):
            self.classify(os.path.join(self.tree.dev, "ttyACM7"), [])

    def test_interface_wins_over_serial_lookup_only_for_plain_names(self):
        self.tree.interface("ttyACM0")
        fox = self.tree.port("ttyACM0", *ESP)
        self.assertEqual(self.classify("ttyACM0", [fox]).kind, devices.WIFI)
        self.assertEqual(self.classify(fox.device, [fox]).kind, devices.FOX)


class AutodetectTest(DevicesTestCase):
    """The five autodetection scenarios."""

    def test_exactly_one_candidate_is_used_by_its_by_id_path(self):
        fox = self.tree.port("ttyACM0", *ESP, link="usb-Espressif_USB_JTAG_serial_debug_unit_F4:12:FA:00:11:22-if00")
        other = self.tree.port("ttyUSB9", *OTHER)
        device = self.autodetect([other, fox])
        self.assertEqual(device.kind, devices.FOX)
        self.assertEqual(device.path, os.path.join(self.tree.by_id,
                                                   "usb-Espressif_USB_JTAG_serial_debug_unit_F4:12:FA:00:11:22-if00"))
        self.assertEqual(device.port.vid, 0x303A)
        self.assertEqual(self.clock.now, 1000.0)

    def test_none_waits_then_exits_2(self):
        said = []
        with self.assertRaises(RunError) as caught:
            self.autodetect([self.tree.port("ttyUSB9", *OTHER)], wait=30, said=said)
        self.assertEqual(str(caught.exception), "no ESP32 serial device found")
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(self.clock.now, 1030.0)
        self.assertEqual(len(said), 1)
        self.assertIn("waiting up to 30 s", said[0])

    def test_wait_never_passes_the_deadline(self):
        deadline = Deadline(12, self.clock)
        with self.assertRaises(RunError):
            self.autodetect([], wait=30, deadline=deadline)
        self.assertEqual(self.clock.now, 1012.0)

    def test_several_candidates_are_listed(self):
        a = self.tree.port("ttyUSB0", *CP210X, link="usb-Silicon_Labs_CP2104_0123ABCD-if00-port0")
        b = self.tree.port("ttyACM0", *ESP)
        c = self.tree.port("ttyUSB1", *FTDI)
        d = self.tree.port("ttyACM1", *CH9102)
        with self.assertRaises(RunError) as caught:
            self.autodetect([a, b, c, d])
        text = str(caught.exception)
        self.assertIn("4 ESP32 serial devices found", text)
        self.assertIn(os.path.join(self.tree.by_id, "usb-Silicon_Labs_CP2104_0123ABCD-if00-port0"), text)
        self.assertIn("10C4:EA60", text)
        self.assertIn("CP2104 USB to UART Bridge Controller", text)
        self.assertIn("0123ABCD", text)
        self.assertIn(b.device, text)
        self.assertIn("303A:1001", text)
        self.assertIn("0403:6001", text)
        self.assertIn("1A86:55D4", text)
        self.assertIn("A50285BI", text)

    def test_fox_appearing_during_the_wait_is_used(self):
        fox = self.tree.port("ttyACM0", *ESP, link="usb-Espressif_USB_JTAG_serial_debug_unit_F4:12:FA:00:11:22-if00")
        clock = self.clock

        def comports():
            return [fox] if clock.now >= 1003.0 else []

        device = devices.autodetect_fox(30, None, comports, clock.sleep, clock, by_id_dir=self.tree.by_id)
        self.assertEqual(device.port.device, fox.device)
        self.assertGreaterEqual(clock.now, 1003.0)
        self.assertLess(clock.now, 1004.0)

    def test_sniffer_is_not_a_fox_candidate(self):
        fox = self.tree.port("ttyUSB0", *CH9102)
        nrf = self.tree.port("ttyACM0", *NRF)
        device = self.autodetect([nrf, fox])
        self.assertEqual(device.port.device, fox.device)
        ports = devices.list_ports(self.comports(nrf, fox))
        sniffer = devices.autodetect_sniffer(ports, self.tree.by_id)
        self.assertEqual(sniffer.kind, devices.SNIFFER)
        self.assertEqual(sniffer.path, nrf.device)

    def test_sniffer_only_when_unambiguous(self):
        a = self.tree.port("ttyACM0", *NRF)
        b = self.tree.port("ttyACM1", *NRF)
        self.assertIsNone(devices.autodetect_sniffer(devices.list_ports(self.comports(a, b))))
        self.assertIsNone(devices.autodetect_sniffer(devices.list_ports(self.comports())))

    def test_hci_only_when_exactly_one_adapter(self):
        self.assertIsNone(devices.autodetect_hci(self.tree.bluetooth))
        self.tree.adapter("hci0")
        self.assertEqual(devices.autodetect_hci(self.tree.bluetooth).path, "hci0")
        self.tree.adapter("hci1")
        self.assertIsNone(devices.autodetect_hci(self.tree.bluetooth))
        self.assertEqual(devices.hci_adapters(self.tree.bluetooth), ["hci0", "hci1"])
        self.assertEqual(devices.hci_adapters(os.path.join(self.tree.root, "missing")), [])


class SelectTest(DevicesTestCase):
    def select(self, names, infos, **kwargs):
        return devices.select(names, 0, None, comports=self.comports(*infos), sleep=self.clock.sleep,
                              clock=self.clock, net_dir=self.tree.net, bluetooth_dir=self.tree.bluetooth,
                              by_id_dir=self.tree.by_id, dev_dir=self.tree.dev, **kwargs)

    def test_wifi_interface_is_never_guessed(self):
        self.tree.interface("wlan0")
        fox = self.tree.port("ttyUSB0", *CP210X)
        selection = self.select([], [fox], want_sniffer=True)
        self.assertEqual(selection.fox.port.device, fox.device)
        self.assertIsNone(selection.wifi)
        self.assertIsNone(selection.sniffer)
        self.assertIsNone(selection.hci)
        selection = self.select(["wlan0"], [fox])
        self.assertEqual(selection.wifi.path, "wlan0")

    def test_given_devices_and_autodetected_rest(self):
        self.tree.adapter("hci0")
        fox = self.tree.port("ttyUSB0", *CP210X)
        nrf = self.tree.port("ttyACM0", *NRF)
        selection = self.select([fox.device], [fox, nrf], want_sniffer=True, want_hci=True)
        self.assertEqual(selection.fox.path, fox.device)
        self.assertEqual(selection.sniffer.path, nrf.device)
        self.assertEqual(selection.hci.path, "hci0")
        selection = self.select(["hci0", nrf.device], [fox, nrf])
        self.assertEqual(selection.fox.path, fox.device)
        self.assertEqual(selection.hci.path, "hci0")
        self.assertEqual(selection.sniffer.path, nrf.device)

    def test_two_foxes_given_is_an_error(self):
        a = self.tree.port("ttyUSB0", *CP210X)
        b = self.tree.port("ttyUSB1", *FTDI)
        with self.assertRaises(RunError) as caught:
            self.select([a.device, b.device], [a, b])
        self.assertIn("two fox devices", str(caught.exception))


class PortTest(unittest.TestCase):
    def test_describe_and_usb_id(self):
        port = devices.Port("/dev/ttyUSB0", 0x10C4, 0xEA60, "CP2104 USB to UART Bridge Controller", "0123ABCD")
        self.assertEqual(port.usb_id(), "10C4:EA60")
        self.assertEqual(port.describe(), "/dev/ttyUSB0  10C4:EA60  CP2104 USB to UART Bridge Controller  0123ABCD")
        bare = devices.Port("/dev/ttyS0", None, None, None, None)
        self.assertEqual(bare.usb_id(), "no USB id")
        self.assertEqual(bare.describe(), "/dev/ttyS0  no USB id  unknown product  no serial number")
        self.assertFalse(bare.is_fox_candidate())
        self.assertFalse(bare.is_sniffer())

    def test_by_id_path_without_the_directory(self):
        self.assertEqual(devices.by_id_path("/dev/ttyUSB0", "/nonexistent/by-id"), "/dev/ttyUSB0")

    def test_main_lists_without_error(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(devices.main([]), 0)
        text = out.getvalue()
        self.assertIn("serial ports:", text)
        self.assertIn("bluetooth adapters:", text)
        self.assertIn("network interfaces:", text)


if __name__ == "__main__":
    unittest.main()
