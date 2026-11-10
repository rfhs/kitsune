"""PlatformIO post extra script: flash a fox that ``flash_verify`` holds in the
ROM bootloader without esptool resetting it, and on a USB-Serial-JTAG fox
without esptool's RAM stub.

``flash.py`` names this file in ``PLATFORMIO_EXTRA_SCRIPTS`` as ``post:<path>``
for one ``pio run -t upload`` of a fox whose bootloader it has confirmed, and
puts the fox's USB stack into ``STACK_VARIABLE``. PlatformIO runs the script
after the platform's ``builder/main.py`` has built ``UPLOADERFLAGS``, so the
esptool command line can still be edited here; no ``platformio.ini`` is
touched.

The platform gives esptool ``--before default-reset`` and ``--after
hard-reset`` (esptool 4 spells them with underscores). A fox that is already
in the ROM bootloader must not be reset into it again, so ``--before``
becomes ``no-reset`` and esptool syncs with the ROM it finds. Without a
before-reset, esptool's own after-reset is not safe on a USB-Serial-JTAG
port: the lines are still both asserted from the open, so asserting RTS
changes nothing and releasing it leaves DTR asserted alone, which arms
download mode instead of restarting the chip. So ``--after`` becomes
``no-reset`` too and ``flash_verify`` resets the fox into the new firmware
itself. On the ESP32-C5 over USB-Serial-JTAG, esptool's RAM stub does not
answer after it is started (the peripheral drops off the bus and the stub's
greeting never arrives), so a USB-Serial-JTAG fox gets ``--no-stub`` and the
ROM bootloader itself writes the flash, which is slower; a UART bridge keeps
the stub, which works there.

Only the ``upload`` target is changed; ``uploadfs`` and the other targets
keep the platform's flags. The functions are plain Python so the tests run
them on a stand-in ``env``; SCons runs the module itself, which is when
``__name__`` is ``SCons.Script``.
"""
import os

# The environment variable flash.py sets to the held fox's USB stack, and the
# stack whose upload runs without esptool's stub. The value is
# usbstack.USB_SERIAL_JTAG, spelt here because PlatformIO's Python cannot
# import foxverify.
STACK_VARIABLE = "FOXVERIFY_HELD_STACK"
USB_SERIAL_JTAG = "usb-serial-jtag"
# esptool's options for the reset before connecting and the one after the
# operation, and its option for talking to the ROM bootloader only.
BEFORE = "--before"
AFTER = "--after"
NO_STUB = "--no-stub"
HELD = "flash_verify holds the fox in the bootloader; esptool runs with %s"


def no_reset(value):
    """esptool's name for no reset, spelt like the value it replaces: esptool
    5 takes ``no-reset``, esptool 4 only ``no_reset``."""
    return "no_reset" if "_" in value else "no-reset"


def held_upload_flags(flags, stack):
    """The platform's ``UPLOADERFLAGS`` with both reset options set to no
    reset and, for a USB-Serial-JTAG fox, ``--no-stub`` in front of them,
    everything else where it was; and the esptool options so set, for the
    line that says what changed."""
    flags = list(flags)
    options = []
    for option in (BEFORE, AFTER):
        if option in flags:
            index = flags.index(option) + 1
            flags[index] = no_reset(flags[index])
            options += [option, flags[index]]
    if stack == USB_SERIAL_JTAG and BEFORE in flags:
        flags.insert(flags.index(BEFORE), NO_STUB)
        options.insert(0, NO_STUB)
    return flags, options


def hold_upload(env, targets, stack, say=print):
    """Rewrite ``env``'s ``UPLOADERFLAGS`` when ``upload`` is among the
    targets of this run and say which esptool options were set, so the
    change shows in ``flash_verify``'s output, which has no pio ``-v``.
    ``stack`` is the held fox's USB stack."""
    if "upload" not in targets or "UPLOADERFLAGS" not in env:
        return
    flags, options = held_upload_flags(env["UPLOADERFLAGS"], stack)
    env.Replace(UPLOADERFLAGS=flags)
    say(HELD % " ".join(options))


def main():
    from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment
    hold_upload(DefaultEnvironment(), COMMAND_LINE_TARGETS, os.environ.get(STACK_VARIABLE))


if __name__ == "SCons.Script":
    main()
