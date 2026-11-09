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

The DTR/RTS sequences live in ``usbstack`` with the USB stacks they belong
to; the bootloader entries are esptool's, chosen by the port's USB id:

- A UART bridge (Silicon Labs CP210x, WCH CH910x, FTDI) gets ``ClassicReset``.
  EN low wakes the chip from deep sleep too.
- The USB-Serial-JTAG peripheral (``303A:1001``: M5 AtomS3 and StampS3, Seeed
  XIAO ESP32-C5) gets ``USBJTAGSerialReset``. The device stays enumerated
  under the same path and the ROM prints its boot log through it, or drops
  off the bus for a moment and is opened again under the same by-id path.
- The Arduino Nano ESP32 (``2341:0070``) runs TinyUSB, and ``pio run -t
  upload`` flashes it with dfu-util through a DFU interface that its
  application provides, writing the new image into the next OTA partition
  while the old one runs. The ROM bootloader has no such interface, so a Nano
  in the bootloader could not be flashed at all; ``enter`` says so and leaves
  it running.
- Any other port is left alone with a line saying why.

Opening the port does not reset the chip on any stack (``usbstack.open_port``).
Both entry sequences end with DTR and RTS released, the state esptool leaves
with ``--after no_reset``, and the kernel's hang-up on close releases lines
that are already released, so closing does not reset it either. ``release``
is the hard reset ``verify`` uses, ``serial_fox.SerialSource.reset``, which
is ``usbstack.hard_reset`` for the stack ``enter`` recorded in the ``Hold``.
"""
from __future__ import annotations

import time
from typing import Callable, NamedTuple, Optional

from . import devices, usbstack
from .report import Deadline, RunError
from .serial_fox import PortGone, SerialSource

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
    not happen. ``port`` is the fox's serial port record, which picks the
    sequences."""

    held: bool
    path: str
    port: Optional[devices.Port]


def _open(path: str, port: Optional[devices.Port], deadline: Deadline,
          sleep: Callable[[float], None]) -> Optional[SerialSource]:
    """The port opened at 115200 with the lines of its stack, tried again
    until the deadline while a device that just enumerated is still
    settling."""
    while True:
        try:
            return SerialSource(path, sleep=sleep, port=port)
        except OSError:
            if deadline.expired():
                return None
            sleep(min(RETRY_SECONDS, deadline.remaining()))


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
    stack = usbstack.usb_stack(fox.port)
    if stack is None:
        usb_id = fox.port.usb_id() if fox.port is not None else "no USB id"
        say(UNKNOWN_SKIPPED % (fox.path, usb_id if usb_id == "no USB id" else "USB id " + usb_id))
        return Hold(False, fox.path, fox.port)
    if stack == usbstack.TINYUSB:
        say(NANO_SKIPPED % fox.path)
        return Hold(False, fox.path, fox.port)
    deadline = Deadline(CONFIRM_SECONDS, clock)
    held = False
    confirmed = False
    for attempt in range(ATTEMPTS):
        source = _open(fox.path, fox.port, deadline, sleep)
        if source is None:
            break
        held = True
        try:
            try:
                usbstack.enter_bootloader(source.serial, stack, sleep)
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
    return Hold(held, fox.path, fox.port)


def release(hold: Hold, say: Callable[[str], None],
            sleep: Callable[[float], None] = time.sleep) -> None:
    """Reset a held fox back into its application with the hard reset
    ``verify`` uses, and say so; a fox that cannot be reached is said too."""
    try:
        source = SerialSource(hold.path, sleep=sleep, port=hold.port)
    except OSError:
        say(NOT_RELEASED % hold.path)
        return
    try:
        source.reset()
    finally:
        source.close()
    say(RELEASED % hold.path)
