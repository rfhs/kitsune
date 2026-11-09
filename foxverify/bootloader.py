"""Put a fox into the ROM bootloader and hold it there while ``flash_verify`` builds.

A fox that is awake for a few seconds and then deep-sleeps is hard to flash:
the build takes a minute or more, and on the boards whose serial port is the
chip's own USB peripheral the port is gone for the whole sleep, so esptool
finds nothing when the build is done. The ROM bootloader in download mode has
no timeout and never sleeps. ``enter`` puts the chip there the moment its port
appears and confirms it with the ROM's ``waiting for download`` line; the
build runs after that, and esptool's own reset at the start of the upload
restarts a chip that is already in download mode into download mode again.
``release`` resets a held chip back into its application when the upload did
not happen, so a failed build or a Ctrl-C leaves the fox running its old
firmware.

The sequences are esptool's (``esptool/reset.py`` in esptool 4.5.1, which the
espressif32 6.7.0 platform ships, and ``esp_pylib/serial_reset.py`` for the
esptool 5.4.0 of the pioarduino platform; the two agree), chosen by the port's
USB id:

- A UART bridge (Silicon Labs CP210x, WCH CH910x, FTDI) drives EN from RTS and
  IO0 from DTR through two transistors, so a line pulls its pin low only while
  the other line is released. ``ClassicReset``: DTR off with RTS on (EN low,
  IO0 high: the chip is held in reset), 0.1 s, DTR on with RTS off (EN high,
  IO0 low: the chip starts and samples IO0), 0.05 s, DTR off (IO0 released).
  EN low wakes the chip from deep sleep too.
- The USB-Serial-JTAG peripheral (``303A:1001``: M5 AtomS3 and StampS3, Seeed
  XIAO ESP32-C5) implements that circuit in hardware
  (``USB_SERIAL_JTAG_CHIP_RST_REG``) and the Arduino core's ``HWCDC.cpp``
  never looks at the line state, so ``USBJTAGSerialReset`` walks the lines
  through the states the peripheral recognises, 0.1 s apart. The device stays
  enumerated under the same path and the ROM prints its boot log through it.
- The Arduino Nano ESP32 (``2341:0070``) runs TinyUSB, and ``pio run -t
  upload`` flashes it with dfu-util through a DFU interface that its
  application provides, writing the new image into the next OTA partition
  while the old one runs. The ROM bootloader has no such interface, so a Nano
  in the bootloader could not be flashed at all; ``enter`` says so and leaves
  it running.
- Any other port is left alone with a line saying why.

pyserial asserts DTR and RTS when it opens a port. On both circuits that is
the state in which neither EN nor IO0 is pulled low, so opening does not
reset the chip. Both sequences end with DTR and RTS released, the state
esptool leaves with ``--after no_reset``, and the kernel's hang-up on close
releases lines that are already released, so closing does not reset it
either. ``release`` is the hard reset ``verify`` uses,
``serial_fox.SerialSource.reset``.
"""
from __future__ import annotations

import time
from typing import Callable, NamedTuple, Optional

from . import devices
from .report import Deadline, RunError
from .serial_fox import PortGone, SerialSource

UART_BRIDGE = "uart bridge"
USB_SERIAL_JTAG = "usb-serial-jtag"
TINYUSB = "tinyusb"

USB_SERIAL_JTAG_ID = (0x303A, 0x1001)
NANO_ID = (0x2341, 0x0070)
UART_BRIDGE_VENDORS = {0x10C4, 0x1A86, 0x0403}

# esptool's delays. ClassicReset holds EN low for ENTER_BOOT_SECONDS and IO0
# low for RESET_DELAY_SECONDS after EN rises; USBJTAGSerialReset pauses
# JTAG_STEP_SECONDS between its phases.
ENTER_BOOT_SECONDS = 0.1
RESET_DELAY_SECONDS = 0.05
JTAG_STEP_SECONDS = 0.1
# How long the ROM's boot log is waited for after the sequence, and how long
# one read of it blocks.
CONFIRM_SECONDS = 3.0
READ_SECONDS = 0.2
# How often a port that is not ready yet is tried again, and how many times a
# sequence that lost the device halfway is sent again after RETRY_SECONDS, as
# esptool's ResetStrategy does.
RETRY_SECONDS = 0.5
ATTEMPTS = 3
WAITING_FOR_DOWNLOAD = "waiting for download"

IN_BOOTLOADER = "fox on %s: in the bootloader, building"
NOT_CONFIRMED = "could not put the fox into the bootloader, flashing the old way"
NANO_SKIPPED = ("fox on %s: the Arduino Nano ESP32 is flashed by dfu-util through its running "
                "application, which the ROM bootloader does not have; flashing the old way")
UNKNOWN_SKIPPED = "fox on %s: %s; not a USB bridge the script knows, flashing the old way"
RELEASED = "fox on %s: reset back into its application"
NOT_RELEASED = "fox on %s: could not reset it; press its reset button"


class Hold(NamedTuple):
    """What ``enter`` did. ``held`` is true once a reset sequence has started
    reaching the fox, whether or not the bootloader was confirmed, so
    ``release`` puts the fox back into its application when the upload does
    not happen."""

    held: bool
    path: str


def usb_stack(port: Optional[devices.Port]) -> Optional[str]:
    """Which reset sequence a port's USB id calls for, or None for a port the
    script does not know."""
    if port is None or port.vid is None:
        return None
    if (port.vid, port.pid) == USB_SERIAL_JTAG_ID:
        return USB_SERIAL_JTAG
    if (port.vid, port.pid) == NANO_ID:
        return TINYUSB
    if port.vid in UART_BRIDGE_VENDORS:
        return UART_BRIDGE
    return None


def set_dtr(port, state: bool) -> None:
    port.dtr = state


def set_rts(port, state: bool) -> None:
    """RTS, then DTR written again with its current value, as esptool does, so
    the control requests a board sees are the ones it answers to esptool."""
    port.rts = state
    port.dtr = port.dtr


def classic_reset(port, sleep: Callable[[float], None]) -> None:
    """esptool's ClassicReset into the bootloader, for a UART bridge."""
    set_dtr(port, False)  # IO0 high
    set_rts(port, True)  # EN low, chip in reset
    sleep(ENTER_BOOT_SECONDS)
    set_dtr(port, True)  # IO0 low
    set_rts(port, False)  # EN high, chip starts and samples IO0
    sleep(RESET_DELAY_SECONDS)
    set_dtr(port, False)  # IO0 released


def usb_jtag_reset(port, sleep: Callable[[float], None]) -> None:
    """esptool's USBJTAGSerialReset into the bootloader, for the USB-Serial-JTAG
    peripheral. RTS changes before DTR in the third phase so the lines pass
    through both asserted rather than both released."""
    set_rts(port, False)
    set_dtr(port, False)  # idle
    sleep(JTAG_STEP_SECONDS)
    set_dtr(port, True)  # IO0 low
    set_rts(port, False)
    sleep(JTAG_STEP_SECONDS)
    set_rts(port, True)  # EN low
    set_dtr(port, False)
    set_rts(port, True)
    sleep(JTAG_STEP_SECONDS)
    set_dtr(port, False)
    set_rts(port, False)  # EN high, chip starts in download mode


def _open(path: str, deadline: Deadline, sleep: Callable[[float], None]) -> Optional[SerialSource]:
    """The port opened at 115200 with DTR and RTS asserted, tried again until
    the deadline while a device that just enumerated is still settling."""
    while True:
        try:
            return SerialSource(path, sleep=sleep)
        except OSError:
            if deadline.expired():
                return None
            sleep(min(RETRY_SECONDS, deadline.remaining()))


def _send(stack: str, source: SerialSource, sleep: Callable[[float], None]) -> None:
    if stack == UART_BRIDGE:
        classic_reset(source.serial, sleep)
    else:
        usb_jtag_reset(source.serial, sleep)


def _confirm(source: SerialSource, deadline: Deadline) -> bool:
    """True when the ROM's ``waiting for download`` line arrives before the
    deadline. A device that drops off the bus during the reset is opened
    again under the same path and read on."""
    seen = ""
    while not deadline.expired():
        try:
            text = source.read(min(READ_SECONDS, deadline.remaining()))
        except PortGone:
            try:
                source.reopen(deadline)
            except RunError:
                return False
            continue
        if text:
            seen = (seen + text)[-4 * len(WAITING_FOR_DOWNLOAD):]
            if WAITING_FOR_DOWNLOAD in seen:
                return True
    return False


def enter(fox: devices.Device, say: Callable[[str], None],
          sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic) -> Hold:
    """Put the fox into the ROM bootloader, confirm it and say what happened.
    A fox the sequences do not fit, or one whose bootloader could not be
    confirmed, is flashed the old way; nothing here exits."""
    stack = usb_stack(fox.port)
    if stack is None:
        usb_id = fox.port.usb_id() if fox.port is not None else "no USB id"
        say(UNKNOWN_SKIPPED % (fox.path, usb_id if usb_id == "no USB id" else "USB id " + usb_id))
        return Hold(False, fox.path)
    if stack == TINYUSB:
        say(NANO_SKIPPED % fox.path)
        return Hold(False, fox.path)
    deadline = Deadline(CONFIRM_SECONDS, clock)
    held = False
    confirmed = False
    for attempt in range(ATTEMPTS):
        source = _open(fox.path, deadline, sleep)
        if source is None:
            break
        held = True
        try:
            try:
                _send(stack, source, sleep)
            except OSError:
                # The device dropped off the bus halfway; esptool opens it
                # again and sends the whole sequence again.
                if attempt + 1 < ATTEMPTS and not deadline.expired():
                    sleep(min(RETRY_SECONDS, deadline.remaining()))
                    continue
                break
            confirmed = _confirm(source, deadline)
            break
        finally:
            source.close()
    say(IN_BOOTLOADER % fox.path if confirmed else NOT_CONFIRMED)
    return Hold(held, fox.path)


def release(hold: Hold, say: Callable[[str], None],
            sleep: Callable[[float], None] = time.sleep) -> None:
    """Reset a held fox back into its application with the hard reset
    ``verify`` uses, and say so; a fox that cannot be reached is said too."""
    try:
        source = SerialSource(hold.path, sleep=sleep)
    except OSError:
        say(NOT_RELEASED % hold.path)
        return
    try:
        source.reset()
    except OSError:
        say(NOT_RELEASED % hold.path)
        return
    finally:
        source.close()
    say(RELEASED % hold.path)
