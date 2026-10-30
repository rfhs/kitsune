RF CTF Fox code

[![Build Test](https://github.com/rfhs/kitsune/actions/workflows/build-test.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/build-test.yaml)
[![Report Format](https://github.com/rfhs/kitsune/actions/workflows/report-format.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/report-format.yaml)
[![Shell Scripts](https://github.com/rfhs/kitsune/actions/workflows/shell-scripts.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/shell-scripts.yaml)


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

## Working on the code

### Layout

Each challenge is its own PlatformIO project: `bluetooth/classic_discoverable`, `bluetooth/iBeacon`, `wifi/wifi_ap_client`, `zigbee/zigbee_coordinator`. `non-kitsune-foxes/` holds stubs for foxes that aren't firmware, so the conference report covers them too.

`include/` at the repo root is shared by every project through a `<project>/include` symlink. A change there changes every challenge, so build them all.

Inside a project, `src/main.cpp` includes `src/current_conf.h`, a symlink to one of the conference headers in `src/conferences/`:
- `9999skel.h` is the template. Its identifiers are placeholders that `make_conference` replaces.
- `9999demo.h` has working demo values and is what the committed `current_conf.h` points at. Never commit the symlink pointing anywhere else.
- `<year><conference>.h` files are real conferences, rolled from the skel.

Each header has one block per difficulty (`#if defined(EASY)`, `#if defined(HARD)`, ...) and every tunable is a `#define` inside it.

### Conferences and reports

`./make_conference_full <name>` runs each project's `make_conference`, which copies `9999skel.h` to `<year><name>.h` with fresh identifiers, then points every `current_conf.h` at the new header and writes `<year><name>.txt`, the report handed to foxes and hunters. `./switch_conference <year><name>` repoints the symlinks later and `./create_report <year><name>` regenerates the report. Reports are gitignored because they hold the flags; don't commit one.

The report is made by grepping the conference headers for `RFHS_CHALLENGE_NAME`, `FOX_KEYWORDS`, `NAME`, `UUID`, `MAC_ADDR`, `FSSID`, `CHANNEL` and `PAN_ID`. **Every line containing one of those words lands in the report, comments included.** Keep them out of comments in conference headers, apart from the intended `// RFHS_CHALLENGE_NAME` and `// FOX_KEYWORDS` lines. `./qa/report-format` catches a leak.

The flags come from `threewords`, which reads `/usr/share/dict/cracklib-words`. Debian and Ubuntu ship that list as `cracklib-small`; `qa/setup` adds the symlink. `dos2unix` and `uuidgen` (package `uuid-runtime` on Debian and Ubuntu) are needed too. Rolling a conference on a machine missing any of these leaves empty flags or UUIDs in the report; `./qa/report-format` catches both.

### Adding a tunable

1. Define it in every difficulty block of `9999skel.h` and `9999demo.h`, with a comment giving the range, what any special value means, and what a hunter will see change.
2. In the shared header for the challenge: refuse bad values at compile time with `#error`, apply the value, then read it back in the check function and refuse to run on a mismatch so the fox shows the fatal LED instead of transmitting something other than what the report says. `CHANNEL` and `PAN_ID` in `include/rfhszigbee.h` show the pattern.
3. If it should be different for every fox at every conference, give it a placeholder value in the skel and a `sed` in that project's `make_conference`. The randomizer must never produce a placeholder value, or a later `sed` replaces it again.
4. If hunters need it, add it to the grep in `create_report` and `make_conference_full`, and a line pattern plus field name in `qa/verify-report`.
5. Build every environment of the project with `./qa/build-test <project>` and run `./qa/report-format`.

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
```
`qa/build-test` puts the `current_conf.h` symlinks back when it finishes. `qa/setup` is what CI installs first; locally you only need `pio` on your PATH, `cracklib-runtime`, `dos2unix` and `uuid-runtime` for `qa/report-format`, and `shellcheck`, `dash`, `mksh` and `busybox` for `qa/shell-lint`.

Your machine is not the CI runner. The runner is Ubuntu, where `/bin/sh` is dash, not bash, and it has only what `qa/setup` installs; a script can pass every local check and fail there. Before you push a change to a script, a workflow or anything under `qa/`, run it the way CI will:
```
./qa/in-ubuntu                                                   # qa/report-format in an ubuntu:24.04 container
./qa/in-ubuntu ./qa/build-test zigbee/zigbee_coordinator seeed_xiao_esp32c5   # one CI job, slow the first time
```
It needs docker or podman, copies your checkout into the container so nothing is written back, and keeps the PlatformIO toolchains in a volume between runs. Treat every failure as real. If one looks like a missing tool, the fix is a line in `qa/setup`, not an excuse.
