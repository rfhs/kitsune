RF CTF Fox code

[![Build Test](https://github.com/rfhs/kitsune/actions/workflows/build-test.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/build-test.yaml)
[![Report Format](https://github.com/rfhs/kitsune/actions/workflows/report-format.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/report-format.yaml)
[![Shell Scripts](https://github.com/rfhs/kitsune/actions/workflows/shell-scripts.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/shell-scripts.yaml)
[![Guard Test](https://github.com/rfhs/kitsune/actions/workflows/guard-test.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/guard-test.yaml)
[![Verify Test](https://github.com/rfhs/kitsune/actions/workflows/verify-test.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/verify-test.yaml)


|Hardware |Bluetooth iBeacon |Bluetooth Classic Discoverable |WiFi AP |WiFi Client |Zigbee Coordinator |
|------------------- | :---------: | :------: | :-----: | :-----: | :-----: |
|M5Stack Atom-lite |✅|✅|✅|✅|❌|
|M5Stack AtomS3-lite |✅|❌|✅|✅|❌|
|M5Stack StampS3 |✅|❌|✅|✅|❌|
|Arduino Nano ESP32 |✅|❌|✅|✅|❌|
|Seeed XIAO ESP32C5 |❌|❌|✅|✅|✅|

We will accept PRs to extend support to other platformio supported hardware.

We have powered our foxes using these batteries:
- https://www.amazon.com/dp/B0C8G8Y3JF
- https://www.amazon.com/dp/B0D2L2Z6VQ

You can use any battery you like, as long as it supplies 5v and does NOT have a low power cut off.  Batteries meant for charging things like cell phones automatically turn off when the draw is low, this means when the esp32 takes a short sleep cycle it never wakes up.

To quickly install platformio you can use a venv like this:
```
python3 -m venv pio
source pio/bin/activate
pip install -U platformio
```
The ESP32-C5 boards use the [pioarduino](https://github.com/pioarduino/platform-espressif32) fork of the espressif32 platform, which needs Python 3.10 or newer.

## Verifying a fox

Each project has a `verify` script next to its `make_conference` that proves a freshly flashed fox transmits what `src/current_conf.h` says. It resets the fox, reads the boot readback over serial, listens for the fox on the air with a sniffer, and prints one row per conference value:
```
cd wifi/wifi_ap_client
sudo ./verify wlan1                       # fox autodetected, wlan1 is the monitor mode card
./verify /dev/ttyACM1 --serial-only       # two ESP32s plugged in, no radio check
sudo ./verify hci0 --no-reset             # Classic or iBeacon: wait for the fox's own wake instead of resetting it
```
```
./verify [DEVICE ...] [--serial-only] [--no-reset] [--timeout 60] [--wait-for-fox 30] [-v]
```
Every `DEVICE` is a plain name and the script works out what it is: a network interface (`wlan1`) is the Wi-Fi sniffer, `hciN` is the Bluetooth adapter, a serial port with the nRF52840 sniffer's USB id (`1915:154B`) is the 802.15.4 sniffer and any other serial port is the fox. Without a fox on the command line the one ESP32 serial device is used; if there is none the script waits `--wait-for-fox` seconds for a native USB board to wake, and if there are several it lists them and asks for one. The nRF sniffer and a lone `hci0` are found on their own; a Wi-Fi interface never is, because putting the wrong card into monitor mode takes the laptop offline. The whole run stays under `--timeout` seconds, 60 by default.

The table has the columns `value | header | serial | air | verdict`. `pass` means header, serial and air agree; `FAIL` means any of them differs, and the exit status is 1; `serial` is a value that is not on the air by design (the sleep timers, the PSK text, `MAX_CLIENTS`, `TXPOWER`, `EXT_PAN_ID`) and agrees between header and serial; `unverified` is a value the sniffer should have seen but did not within the time, with the reason. A device that is not a fox, a fox built for another project, a fox built from another conference header, a missing tool or a missing privilege is said in plain words and the exit status is 2. Without a sniffer the run is serial-only and says so.

What each fox needs on the air, and the privilege for it:
- Bluetooth Classic: `btmgmt` (bluez) runs an inquiry on `hci0`; needs root or `CAP_NET_ADMIN`.
- iBeacon: an active BLE scan with [bleak](https://github.com/hbldh/bleak) on `hci0`; no root needed.
- Wi-Fi: `tshark`, `iw` and `ip` put the named card into monitor mode and read beacons (AP) or probe requests (client); needs root. The card's type and state are put back when the script ends, including on Ctrl-C.
- Zigbee: an nRF52840 dongle running Nordic's 802.15.4 sniffer firmware (the one Kismet uses) and `tshark`; no root needed, only access to the dongle's serial port. `PACKET_INTERVAL` needs two Link Status frames, so an interval above about 20 seconds cannot be confirmed within the 60 second limit and is reported `unverified`.

The `verify` scripts never call `sudo` themselves; run them under it when the check above needs root, or use `flash_verify` below, which does. Packages:
- Debian and Ubuntu: `python3-serial python3-bleak tshark bluez iw`
- Arch: `python-pyserial python-bleak wireshark-cli bluez-utils iw`
- Gentoo: `dev-python/pyserial` from the main tree; `bleak` is only in the GURU overlay, so either enable that or use a venv that still sees the system packages:
```
python3 -m venv --system-site-packages .venv && .venv/bin/pip install bleak
sudo .venv/bin/python3 bluetooth/iBeacon/verify hci0
```
The iBeacon script prints the same hint when `import bleak` fails. Python 3.9 or newer is enough.

### Flashing and verifying in one step

`flash_verify`, next to `verify` in every project, builds one environment of the project's `platformio.ini`, uploads it to the fox and then runs `verify`. The environment comes first; everything after it goes to `verify` unchanged:
```
cd bluetooth/classic_discoverable && ./flash_verify m5atom-hard hci0
cd bluetooth/iBeacon && ./flash_verify m5atom-medium
cd wifi/wifi_ap_client && ./flash_verify m5atom-easy-ap wlan1
cd zigbee/zigbee_coordinator && ./flash_verify seeed-xiao-esp32c5-easy-coordinator -v
```
Run it as yourself, never under `sudo`: PlatformIO would leave root-owned files in `~/.platformio` and the project's `.pio/`, so the script refuses to run as root. When `verify` needs root for the devices given (Classic with an adapter, Wi-Fi with an interface) the script asks for the `sudo` password before the build and runs only the `verify` step through `sudo`. The fox's serial port is autodetected with the rules above unless given, and is the upload port; a native USB board that comes back under another name after the flash is found again. The tool checks `verify` would make run before the build, so a missing `tshark` is said before a minute of compiling; an unknown environment exits 2 with the list of the project's environments. Before the build one line names the project, the environment and the conference `src/current_conf.h` points at, which is the moment to Ctrl-C if it is the wrong one.

The shared code is in `foxverify/` at the repo root; `python3 -m foxverify.conf <header>` dumps a conference header as JSON and `python3 -m foxverify.devices` lists what the device rules see on your machine. `./qa/verify-test` runs its unit tests.

## Working on the code

### Layout

Each challenge is its own PlatformIO project: `bluetooth/classic_discoverable`, `bluetooth/iBeacon`, `wifi/wifi_ap_client`, `zigbee/zigbee_coordinator`. `non-kitsune-foxes/` holds stubs for foxes that aren't firmware, so the conference report covers them too.

`include/` at the repo root is shared by every project through a `<project>/include` symlink. A change there changes every challenge, so build them all.

`foxverify/` at the repo root is the Python package behind each project's `verify` and `flash_verify` scripts (see "Verifying a fox"), with its unit tests and recorded serial transcripts under `foxverify/tests/`.

Inside a project, `src/main.cpp` includes `src/current_conf.h`, a symlink to one of the conference headers in `src/conferences/`:
- `9999skel.h` is the template. Its identifiers, and in the Wi-Fi project the PSK, are placeholders that `make_conference` replaces.
- `9999demo.h` has working demo values and is what the committed `current_conf.h` points at. Never commit the symlink pointing anywhere else.
- `<year><conference>.h` files are real conferences, rolled from the skel.

Each header has one block per difficulty (`#if defined(EASY)`, `#if defined(HARD)`, ...) and every tunable is a `#define` inside it. Every tunable has a comment giving its permitted values, and the shared header that uses it refuses to compile anything else: a 5 byte MAC, a passphrase under 8 characters, a Zigbee channel of 5. The error message names the variable and the range. `./qa/guard-test` proves every one of those checks still fires.

### Conferences and reports

`./make_conference_full <name>` runs each project's `make_conference`, which copies `9999skel.h` to `<year><name>.h` with fresh identifiers (MAC addresses, iBeacon UUIDs, Zigbee PAN IDs) and, for every Wi-Fi block, a random WPA2 passphrase of 63 letters and digits, then points every `current_conf.h` at the new header and writes `<year><name>.txt`, the report handed to foxes and hunters. `./switch_conference <year><name>` repoints the symlinks later and `./create_report <year><name>` regenerates the report. Reports are gitignored because they hold the flags; don't commit one.

The report is made by grepping the conference headers for `RFHS_CHALLENGE_NAME`, `FOX_KEYWORDS`, `NAME`, `UUID`, `MAC_ADDR`, `FSSID`, `CHANNEL` and `PAN_ID`. **Every line containing one of those words lands in the report, comments included.** Keep them out of comments in conference headers, apart from the intended `// RFHS_CHALLENGE_NAME` and `// FOX_KEYWORDS` lines. `./qa/report-format` catches a leak.

The flags come from `threewords`, which reads `/usr/share/dict/cracklib-words`. Debian and Ubuntu ship that list as `cracklib-small`; `qa/setup` adds the symlink. `dos2unix` and `uuidgen` (package `uuid-runtime` on Debian and Ubuntu) are needed too. Rolling a conference on a machine missing any of these leaves empty flags or UUIDs in the report; `./qa/report-format` catches both.

### Adding a tunable

1. Define it in every difficulty block of `9999skel.h` and `9999demo.h`, with a comment giving the range, what any special value means, and what a hunter will see change.
2. In the shared header for the challenge: refuse bad values at compile time with `#error` (numbers) or `static_assert` (strings and byte arrays, helpers in `include/rfhsconfcheck.h`), apply the value, then read it back in the check function and refuse to run on a mismatch so the fox shows the fatal LED instead of transmitting something other than what the report says. `CHANNEL` and `PAN_ID` in `include/rfhszigbee.h` show the pattern. The message names the variable and the permitted values, and the comment on the define in the conference header says the same thing.
3. Add a case to `qa/guard-test` for each way the value can be wrong, and run it.
4. If it should be different for every fox at every conference, give it a placeholder value in the skel and a `sed` in that project's `make_conference`. The randomizer must never produce a placeholder value, or a later `sed` replaces it again.
5. If hunters need it, add it to the grep in `create_report` and `make_conference_full`, and a line pattern plus field name in `qa/verify-report`.
6. Give the readback line a regex in `foxverify/serial_fox.py`, add it to the transcripts under `foxverify/tests/fixtures/transcripts/`, and add its row to the project's run in `foxverify/run.py`, so `verify` checks it too.
7. Build every environment of the project with `./qa/build-test <project>` and run `./qa/report-format` and `./qa/verify-test`.

### Adding a board

- Add a board section to the project's `platformio.ini` with an explicit `platform = ${platform.<name>}` and name its environments `<board>-<difficulty>[-<mode>]`. CI builds its matrix from the `board` of every environment, so a new board gets its own job without touching the workflow.
- Add the LED data pin to `include/rfhsledmacros.h`.
- Add a row to the hardware table above.

### Platforms

Platforms are pinned in each `platformio.ini` and every board section names one. `espressif32@~6.7.0` is used for all boards except the ESP32-C5, which needs the pinned pioarduino release because nothing else supports it. The Bluetooth Classic challenge needs the Bluedroid stack from Arduino core 2.x, so don't move the espressif32 pin without checking it. Never use pioarduino's `stable` download URL, its contents change. Bump a pin on purpose, in its own PR, and build everything.

### Shell scripts

A script with `#!/bin/sh` has to work in bash, dash, mksh and busybox ash, so it is POSIX sh only. A script with `#!/bin/bash` has to work in at least bash, and is only worth it when bash makes it clearly more readable; every script here is `/bin/sh`. Everything passes `shellcheck`. `./qa/shell-lint` checks all of that for every script in the repo and CI runs it on each PR. Remember that `sed`'s `e` flag, `system()` and `sh -c` run `/bin/sh` no matter what shebang your script has, so a bash function is invisible to them.

### Testing

CI builds every environment of every project twice, once with the checked in `9999demo` conference and once with a conference freshly rolled off `9999skel`, and checks the generated conference reports line by line. Each project and board pair is its own job so a failure names the board that broke; a board with many environments is split by mode (`ap`, `client`) so one job doesn't set the pace. The same scripts run at home:
```
./qa/build-test                                             # everything, takes a while
./qa/build-test wifi/wifi_ap_client                         # one project
./qa/build-test wifi/wifi_ap_client seeed_xiao_esp32c5      # one board
./qa/build-test wifi/wifi_ap_client seeed_xiao_esp32c5 ap   # one board's -ap environments, one CI job
./qa/build-test list                                        # the jobs CI will run
./qa/report-format                                          # generate and check the conference reports
./qa/shell-lint                                             # shellcheck and parse every shell script
./qa/guard-test [project]                                   # every bad conference value is refused at compile time
./qa/verify-test                                            # pyflakes and the unit tests of the verify scripts
```
`qa/build-test` puts the `current_conf.h` symlinks back when it finishes. `qa/setup` is what CI installs first; locally you only need `pio` on your PATH, `cracklib-runtime`, `dos2unix` and `uuid-runtime` for `qa/report-format`, `shellcheck`, `dash`, `mksh` and `busybox` for `qa/shell-lint`, and `python3-serial`, `python3-pyflakes` and `tshark` for `qa/verify-test` (the one test that decodes a pcap with tshark is skipped without it).

Your machine is not the CI runner. The runner is Ubuntu, where `/bin/sh` is dash, not bash, and it has only what `qa/setup` installs; a script can pass every local check and fail there. Before you push a change to a script, a workflow or anything under `qa/`, run it the way CI will:
```
./qa/in-ubuntu                                                   # qa/report-format in an ubuntu:24.04 container
./qa/in-ubuntu ./qa/build-test zigbee/zigbee_coordinator seeed_xiao_esp32c5   # one CI job, slow the first time
```
It needs docker or podman, copies your checkout into the container so nothing is written back, and keeps the PlatformIO toolchains in a volume between runs. Treat every failure as real. If one looks like a missing tool, the fix is a line in `qa/setup`, not an excuse.
