"""Build, flash and verify a fox in one step.

``main(project)`` is what the four ``<project>/flash_verify`` scripts call::

    ./flash_verify <env> [DEVICE ...] [verify options...]

``<env>`` names an environment of the project's ``platformio.ini``. Every
other argument is handed to the project's ``verify`` unchanged after the
flash, so anything ``verify`` accepts works here. The steps:

1. Refuse to run as root. PlatformIO writes to ``~/.platformio`` and to the
   project's ``.pio/``, and a root run leaves root-owned files in both.
2. Check the environment name and that ``pio`` is on PATH.
3. Resolve the fox's serial port once, with the rules of ``devices``: an
   explicit serial argument that is not the nRF sniffer, else the one ESP32
   serial device, waiting ``--wait-for-fox`` seconds for it to appear.
4. Put the fox into the ROM bootloader at once and confirm it
   (``bootloader.enter``), so a fox that is awake for a few seconds between
   deep sleeps is held from the moment its port appears, through the tool
   checks, the ``sudo`` prompt and the build, instead of sleeping again
   before esptool runs. A fox that cannot be held is flashed the old way.
   From here until the upload has succeeded, every exit resets a held fox
   back into its application first, so a failed check, a failed build or a
   Ctrl-C leaves it running its old firmware.
5. Run the tool checks ``verify`` would run for this project and these
   devices, so a missing ``tshark`` fails before a one-minute build, and
   learn whether ``verify`` needs root. When it does, ``sudo -v`` runs now,
   so the password prompt comes before the build and not after it.
6. Print the project, the environment, the conference ``src/current_conf.h``
   points at and the port, then build and upload with ``pio run``, output
   shown as it arrives. A fox confirmed in the bootloader is uploaded
   without esptool's resets, and on a USB-Serial-JTAG port without esptool's
   stub flasher, through the post extra script ``pio_held_upload`` named in
   the ``PLATFORMIO_EXTRA_SCRIPTS`` environment variable of that one ``pio``
   run; ``--disable-auto-clean`` keeps PlatformIO from treating the extra
   script as a changed configuration and rebuilding everything. esptool then
   leaves the fox in the bootloader and ``bootloader.restart`` resets it into
   the new firmware.
7. Work out the device the fox came back on. A fox the user named is passed
   on as given. An autodetected fox is passed on by its pre-flash path when
   that still exists; when it is gone, because a native USB board
   re-enumerates after a flash and can come back under another name, the
   autodetection runs again with the same wait.
8. Run ``verify``, through ``sudo`` when it needs root, and exit with its
   exit code.
"""
from __future__ import annotations

import argparse
import codecs
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, TextIO, Tuple

from . import bootloader, devices, pio_held_upload, privileges
from .report import RunError
from .run import INTERRUPTED, RUNS, parse_args as parse_verify_args
from .serial_fox import PROJECT_DIRS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT_REFUSED = ("flash_verify must not run as root: PlatformIO would leave root-owned files in "
                "~/.platformio and in the project's .pio/. Run it as yourself; it runs the verify "
                "step through sudo when that step needs root.")
NO_PIO = ("pio not found on PATH. Install PlatformIO as the README says, a venv with "
          "pip install -U platformio, and activate it.")
NO_SUDO = "verify needs root for %s and sudo is not installed"
SUDO_FAILED = "sudo -v failed; verify needs root for %s"
NOTHING_TO_FLASH = "--transcript replays a recording; there is nothing to flash"
PIO_FAILED = "pio run exited with status %d; its last lines:\n  %s"
# How many lines of pio's output a failure message quotes.
TAIL_LINES = 15
# How much of pio's output is kept for those lines.
TAIL_CHARS = 4000
# Seconds between the end of the upload and the look for the fox's port. A
# board that re-enumerates after the flash takes a moment to drop its old
# device node, and a look before that would trust a path about to vanish.
SETTLE_SECONDS = 1.0
# The post extra script that takes esptool's resets, and the stub flasher on a
# USB-Serial-JTAG port, out of the upload of a held fox, and the environment
# variable PlatformIO reads extra scripts from.
HELD_UPLOAD_SCRIPT = os.path.abspath(pio_held_upload.__file__)
EXTRA_SCRIPTS = "PLATFORMIO_EXTRA_SCRIPTS"

_ENV = re.compile(r"^\[env:([^\]]+)\]\s*$")

DESCRIPTION = ("Build ENV, upload it to the fox and run this project's verify script with the "
               "remaining arguments. The fox's serial port is autodetected unless given.")
EPILOG = """\
ENV comes first and is an environment of this project's platformio.ini.
Everything after it goes to ./verify unchanged: devices (wlan1, hci0,
/dev/ttyACM1) and options (--serial-only, --timeout, -v, ...); see
./verify --help. Run as yourself, not as root: when verify needs root for
these devices, sudo asks for the password before the build and runs the
verify step. Exit codes are verify's: 0 when nothing FAILed, 1 on any FAIL,
2 when the run could not happen, including a failed build or upload."""


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="flash_verify", description=DESCRIPTION, epilog=EPILOG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("env", metavar="ENV",
                        help="the environment of this project's platformio.ini to build and upload")
    parser.add_argument("verify_args", nargs=argparse.REMAINDER, metavar="VERIFY_ARG",
                        help="devices and options for ./verify, passed on unchanged")
    return parser.parse_args(argv)


def environments(ini_path: str) -> List[str]:
    """The environment names of a platformio.ini, in file order."""
    names = []
    with open(ini_path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = _ENV.match(line)
            if match:
                names.append(match.group(1).strip())
    return names


def check_environment(project_dir: str, env: str) -> None:
    """``RunError`` listing the project's environments when ``env`` is not one."""
    names = environments(os.path.join(project_dir, "platformio.ini"))
    if env not in names:
        raise RunError("%s is not an environment of %s; pick one of:\n  %s" % (
            env, os.path.relpath(project_dir, REPO), "\n  ".join(names)))


def conference(project_dir: str) -> str:
    """What ``src/current_conf.h`` points at, or the file itself when it is no link."""
    path = os.path.join(project_dir, "src", "current_conf.h")
    try:
        return os.readlink(path)
    except OSError:
        return os.path.relpath(path, project_dir)


def pio_argv(pio: str, project_dir: str, env: str, port: str, held: bool = False) -> List[str]:
    """The upload command. For a held fox the extra script in the environment
    makes PlatformIO see a changed project configuration, which would wipe
    the build directory and rebuild every environment; ``--disable-auto-clean``
    leaves the build directory to SCons's own dependency tracking."""
    argv = [pio, "run", "--project-dir", project_dir, "-e", env]
    if held:
        argv.append("--disable-auto-clean")
    return argv + ["-t", "upload", "--upload-port", port]


def held_environment(environ: Mapping[str, str], stack: Optional[str]) -> Dict[str, str]:
    """The ``pio`` process's environment for the upload of a held fox: the
    caller's, with ``pio_held_upload`` first among the extra scripts and the
    fox's USB stack (empty when unknown) in the variable the script reads. An
    extra-scripts value the user already has is kept behind ours, joined the
    way PlatformIO splits the variable: on newlines when it has one, else on
    commas."""
    env = dict(environ)
    ours = "post:" + HELD_UPLOAD_SCRIPT
    existing = env.get(EXTRA_SCRIPTS)
    if existing:
        ours += ("\n" if "\n" in existing else ", ") + existing
    env[EXTRA_SCRIPTS] = ours
    env[pio_held_upload.STACK_VARIABLE] = stack or ""
    return env


def verify_argv(verify_args: Sequence[str], given: Sequence[str], fox: Optional[str]) -> List[str]:
    """``verify``'s arguments: the user's, in their order, plus the fox's path
    when the user did not name the fox. argparse wants the positional
    devices in one group, so the path goes right before the first device
    the user gave, or at the end when there is none."""
    argv = list(verify_args)
    if fox is None:
        return argv
    if given:
        argv.insert(argv.index(given[0]), fox)
    else:
        argv.append(fox)
    return argv


def stream(argv: Sequence[str], out: TextIO,
           popen: Callable[..., subprocess.Popen] = subprocess.Popen,
           env: Optional[Mapping[str, str]] = None) -> Tuple[int, List[str]]:
    """Run a command, copying its output to ``out`` as it arrives. Returns
    the exit status and the last ``TAIL_LINES`` non-empty lines of the
    output, for the message when the command fails. ``env`` is the command's
    environment, this process's when None."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    tail = ""
    process = popen(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    try:
        with process.stdout as pipe:
            for chunk in iter(lambda: pipe.read1(4096), b""):
                text = decoder.decode(chunk)
                out.write(text)
                out.flush()
                tail = (tail + text)[-TAIL_CHARS:]
        status = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    lines = [line for line in re.split(r"\r\n|\r|\n", tail) if line.strip()]
    return status, lines[-TAIL_LINES:]


class Flash:
    """One build, flash and verify of one project. The callables stand in
    for the machine, so the tests run without a fox, a pio or a sudo."""

    def __init__(self, project: str, args: argparse.Namespace, out: TextIO = sys.stdout,
                 which: Callable[[str], Optional[str]] = shutil.which,
                 euid: Callable[[], int] = os.geteuid,
                 capabilities: Callable[[], int] = privileges.effective_capabilities,
                 comports: Optional[Callable[[], Iterable]] = None,
                 exists: Callable[[str], bool] = os.path.exists,
                 call: Callable[[List[str]], int] = subprocess.call,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 environ: Mapping[str, str] = os.environ):
        self.project = project
        self.env = args.env
        self.verify_args = list(args.verify_args)
        self.out = out
        self.which = which
        self.euid = euid
        self.capabilities = capabilities
        self.comports = comports
        self.exists = exists
        self.call = call
        self.popen = popen
        self.sleep = sleep
        self.clock = clock
        self.environ = environ
        self.project_dir = os.path.join(REPO, PROJECT_DIRS[project])

    def say(self, text: str) -> None:
        self.out.write(text + "\n")
        self.out.flush()

    def run(self) -> int:
        if self.euid() == 0:
            raise RunError(ROOT_REFUSED)
        check_environment(self.project_dir, self.env)
        pio = self.which("pio")
        if pio is None:
            raise RunError(NO_PIO)
        options = parse_verify_args(self.project, self.verify_args)
        run = RUNS[self.project](self.project, options, self.out)
        if run.replay:
            raise RunError(NOTHING_TO_FLASH)
        ports = devices.list_ports(self.comports)
        selection = run.select_devices(comports=self.comports, sleep=self.sleep, clock=self.clock,
                                       exists=self.exists)
        fox = selection.fox
        given = self.fox_given(options.devices, ports)
        hold = bootloader.enter(fox, self.say, self.sleep, self.clock)
        uploaded = False
        try:
            # A serial-only verify leaves every radio alone and needs no tool.
            what = None if run.serial_only else run.check_tools(selection, self.which)
            needs_root = what is not None and not privileges.has_net_admin(self.euid, self.capabilities)
            sudo = None
            if needs_root:
                sudo = self.which("sudo")
                if sudo is None:
                    raise RunError(NO_SUDO % what)
            self.say("project %s, environment %s, conference %s" % (
                os.path.relpath(self.project_dir, REPO), self.env, conference(self.project_dir)))
            self.say("fox on %s%s" % (fox.path, "; verify runs through sudo for %s" % what if needs_root else ""))
            if needs_root and self.call([sudo, "-v"]) != 0:
                raise RunError(SUDO_FAILED % what)
            # A fox confirmed in the bootloader is flashed without esptool
            # resetting it; esptool leaves it in the bootloader afterwards.
            environment = held_environment(self.environ, hold.stack) if hold.confirmed else None
            status, tail = stream(pio_argv(pio, self.project_dir, self.env, fox.path, hold.confirmed),
                                  self.out, self.popen, environment)
            if status != 0:
                raise RunError(PIO_FAILED % (status, "\n  ".join(tail)))
            uploaded = True
        finally:
            # Whatever ends the run before the upload, the fox must not be left
            # in the bootloader.
            if hold.held and not uploaded:
                bootloader.release(hold, self.say, self.sleep)
        if hold.confirmed:
            bootloader.restart(hold, self.say, options.verbose, self.sleep)
        added = None if given else self.fox_after_flash(fox.path, options.wait_for_fox)
        command = ([sudo] if needs_root else []) + [os.path.join(self.project_dir, "verify")]
        command += verify_argv(self.verify_args, options.devices, added)
        self.say("running %s" % " ".join(command))
        return self.call(command)

    def fox_given(self, names: Sequence[str], ports: Sequence[devices.Port]) -> bool:
        """True when one of the user's devices is the fox, so its path is
        passed on as given and never replaced."""
        for name in names:
            if devices.classify(name, ports, exists=self.exists).kind == devices.FOX:
                return True
        return False

    def fox_after_flash(self, path: str, wait: float) -> str:
        """The device an autodetected fox is on after the flash: its pre-flash
        path when that still exists, else what a new autodetection finds."""
        self.sleep(SETTLE_SECONDS)
        if self.exists(path):
            return path
        self.say("%s is gone after the flash; looking for the fox again" % path)
        return devices.autodetect_fox(wait, None, self.comports, self.sleep, self.clock, self.say).path


def main(project: str, argv: Optional[List[str]] = None, out: TextIO = sys.stdout,
         err: TextIO = sys.stderr, **machine) -> int:
    """Run the flash_verify script of ``project``; the exit code is returned.
    ``machine`` holds the stand-ins ``Flash`` accepts."""
    args = parse_args(argv)
    try:
        return Flash(project, args, out, **machine).run()
    except RunError as error:
        out.flush()
        err.write("%s\n" % error)
        return error.exit_code
    except KeyboardInterrupt:
        out.flush()
        err.write("interrupted\n")
        return INTERRUPTED
