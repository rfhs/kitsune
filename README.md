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

## Testing

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
