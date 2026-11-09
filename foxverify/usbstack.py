"""The USB stacks behind a fox's serial port and the DTR/RTS line sequences
that open the port, reset the chip into its application or hold it in the
ROM bootloader, one set per stack.

This module is the only place that writes DTR or RTS. ``serial_fox`` opens
and resets through it for ``verify``, ``bootloader`` holds and releases
through it for ``flash_verify``. The stack is read from the port's USB id,
``usb_stack``:

- **UART bridge** (Silicon Labs CP210x ``10C4``, WCH ``1A86``, FTDI ``0403``:
  the M5 Atom). RTS drives EN and DTR drives IO0 through two transistors, so
  a line pulls its pin low only while the other line is released and both
  asserted pulls nothing. pyserial asserts both when it opens, so opening
  leaves the chip alone.
- **USB-Serial-JTAG** (``303A:1001``: M5 AtomS3 and StampS3, Seeed XIAO
  ESP32-C5). The peripheral itself answers the CDC-ACM line-state request and
  the Arduino core's ``HWCDC.cpp`` never sees it. Its table (ESP32-C5 TRM
  v1.1 table 37.3-2, the same in the ESP32-S3 and ESP32-C3 manuals) is, in
  pyserial's terms where ``True`` is asserted: RTS and DTR both released
  clears a download-mode flag; DTR asserted alone sets that flag; RTS
  asserted alone resets the chip, which then boots into download mode when
  the flag is set and from flash when it is clear; both asserted does
  nothing. The flag is a latch, so a port left with DTR asserted alone arms
  the next reset for the bootloader. The kernel asserts both lines when the
  port opens, which does nothing; ``open_port`` then releases RTS before
  DTR, so the lines reach the cleared state without passing through RTS
  asserted alone, and keeps them there: opening a running fox never resets
  it and clears any flag another program left. ``hard_reset`` is esptool's
  for this peripheral (``esp_pylib/serial_reset.py`` ``hard_reset``, as
  esptool's ESP32-C5 target calls it): RTS asserted for 0.2 s with DTR left
  released, then released again and 0.2 s for the device to settle, which
  can include dropping off the bus and enumerating again.
- **TinyUSB** (``2341:0070``: the Arduino Nano ESP32). The application's
  USB stack owns the lines. ``USBCDC.cpp`` reacts to them in two ways only:
  a four-step line-state dance and a 1200 bps line coding, both of which
  restart the chip into the ROM bootloader, never into the application. So
  ``hard_reset`` sends nothing and returns None, and a caller waits for the
  fox's own wake. DTR stays asserted because ``USBCDC::write`` drops output
  while it is released.
- **Unknown id**: the UART bridge sequence, which is what every bridge the
  script does not know by name most likely wires.

The hard reset for a UART bridge: DTR released and RTS asserted (EN low,
IO0 high) for 0.1 s, RTS released (EN high: the chip starts and samples IO0
high, so it boots from flash), 0.1 s, then DTR and RTS asserted again, DTR
first. The pause keeps the brief IO0 dip of asserting DTR alone away from
the moment EN rises, and asserting RTS before DTR would pulse EN a second
time.

The bootloader entries are esptool's ``ClassicReset`` for a bridge and
``USBJTAGSerialReset`` for the USB-Serial-JTAG peripheral (esptool 4.5.1
``esptool/reset.py``, esptool 5.4.0 ``esp_pylib/serial_reset.py``
``classic_bootloader_reset`` and ``usb_jtag_bootloader_reset``; the two
agree). Both end with the lines released, the state esptool leaves with
``--after no_reset``, so closing the port afterwards resets nothing.
``set_rts`` writes DTR again with its current value after every RTS write,
as esptool does for Windows' ``usbser.sys``, so a board sees the same
control requests from this script as from esptool.
"""
from __future__ import annotations

import time
from typing import Callable, NamedTuple, Optional

from . import devices

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
# The hard reset's timing: a UART bridge holds EN low for RESET_PULSE_SECONDS
# and waits as long again before the lines are asserted; the USB-Serial-JTAG
# peripheral holds reset for USB_HOLD_SECONDS and is left alone for
# USB_SETTLE_SECONDS after the release, esptool's 0.2 and 0.2.
RESET_PULSE_SECONDS = 0.1
USB_HOLD_SECONDS = 0.2
USB_SETTLE_SECONDS = 0.2


def usb_stack(port: Optional[devices.Port]) -> Optional[str]:
    """Which line sequences a port's USB id calls for, or None for a port the
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


def open_port(port, stack: Optional[str]) -> None:
    """Open a configured pyserial port without resetting the chip behind it.

    pyserial writes DTR before RTS when it opens, after the kernel has
    asserted both. On the USB-Serial-JTAG peripheral both asserted does
    nothing and RTS asserted alone is the reset, so RTS is released by the
    open and DTR only after it; the lines end released, the state that
    clears the peripheral's download-mode flag. Every other stack keeps both
    lines asserted, which pulls nothing on a bridge's circuit and lets a
    TinyUSB port send its output.
    """
    port.dtr = True
    if stack == USB_SERIAL_JTAG:
        port.rts = False
        port.open()
        port.dtr = False
        return
    port.rts = True
    port.open()


class Reset(NamedTuple):
    """What ``hard_reset`` did: ``released`` is the moment on the caller's
    clock at which the chip left reset and began to boot, None for a stack
    that has no reset; ``dropped`` is true when the device left the bus
    during the sequence, so the port is dead and has to be opened again."""

    released: Optional[float]
    dropped: bool


def hard_reset(port, stack: Optional[str], sleep: Callable[[float], None],
               wall: Callable[[], float] = time.time) -> Reset:
    """Restart the chip into its application.

    The lines are expected released on a USB-Serial-JTAG port, as
    ``open_port`` and ``usb_jtag_reset`` leave them, so the reset finds the
    download-mode flag clear. A chip that drops off the bus while it is held
    restarted at the moment reset was asserted, which is then the stamp. An
    ``OSError`` from the first write is left to the caller: the device was
    gone before anything reached it.
    """
    if stack == TINYUSB:
        return Reset(None, False)
    if stack == USB_SERIAL_JTAG:
        set_rts(port, True)  # RTS alone: reset asserted
        asserted = wall()
        try:
            sleep(USB_HOLD_SECONDS)
            set_rts(port, False)  # both released: the chip boots from flash
        except OSError:
            return Reset(asserted, True)
        released = wall()
        sleep(USB_SETTLE_SECONDS)
        return Reset(released, False)
    port.dtr = False  # IO0 high
    released = None
    try:
        port.rts = True  # EN low
        sleep(RESET_PULSE_SECONDS)
        port.rts = False  # EN high: the chip boots from flash
        released = wall()
        sleep(RESET_PULSE_SECONDS)
        port.dtr = True
        port.rts = True
    except OSError:
        return Reset(wall() if released is None else released, True)
    return Reset(released, False)


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
    peripheral: the download-mode flag set, then the reset with the flag set,
    then both lines released. RTS changes before DTR in the third phase so
    the lines pass through both asserted rather than both released."""
    set_rts(port, False)
    set_dtr(port, False)  # both released: flag cleared
    sleep(JTAG_STEP_SECONDS)
    set_dtr(port, True)  # DTR alone: flag set
    set_rts(port, False)
    sleep(JTAG_STEP_SECONDS)
    set_rts(port, True)  # both asserted: nothing yet
    set_dtr(port, False)  # RTS alone: reset, into download mode
    set_rts(port, True)
    sleep(JTAG_STEP_SECONDS)
    set_dtr(port, False)
    set_rts(port, False)  # both released


def enter_bootloader(port, stack: str, sleep: Callable[[float], None]) -> None:
    """The bootloader entry for a stack that has one."""
    if stack == USB_SERIAL_JTAG:
        usb_jtag_reset(port, sleep)
    else:
        classic_reset(port, sleep)
