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
Every `DEVICE` is a plain name and the script works out what it is: a network interface (`wlan1`) is the Wi-Fi sniffer, `hciN` is the Bluetooth adapter, a serial port with the nRF52840 sniffer's USB id (`1915:154A` or `1915:154B`, depending on the firmware release) is the 802.15.4 sniffer and any other serial port is the fox. Without a fox on the command line the one serial port with a fox USB id is used: Espressif `303A` (the M5 AtomS3, StampS3 and XIAO ESP32-C5 USB-Serial-JTAG), Arduino `2341:0070` (the Nano ESP32's TinyUSB), or a CP210x `10C4`, WCH `1A86` or FTDI `0403` bridge (the M5 Atom). If there is none the script waits `--wait-for-fox` seconds for a native USB board to wake, and if there are several it lists them and asks for one. The nRF sniffer and a lone `hci0` are found on their own; a Wi-Fi interface never is, because putting the wrong card into monitor mode takes the laptop offline. The whole run stays under `--timeout` seconds, 60 by default.

The reset is the USB stack's own restart sequence, the one esptool runs after a flash, chosen by the fox's USB id (the EN pulse through a bridge's DTR/RTS circuit on the Atom, the USB-Serial-JTAG peripheral's RTS pulse with DTR left released on the AtomS3, StampS3 and XIAO ESP32-C5), opening the port never resets a running fox, and a reset that still lands the chip in the ROM bootloader is said and repeated once before the script asks for the board's reset button. The Arduino Nano ESP32 cannot be reset over its serial port, because its TinyUSB stack only knows how to enter the bootloader, so `verify` says so and waits for the fox's own wake as with `--no-reset`.

The table has the columns `value | header | serial | air | verdict`. `pass` means header, serial and air agree; `FAIL` means any of them differs, and the exit status is 1; `serial only` is a value the air does not decide (the PSK text, `MAX_CLIENTS`, `TXPOWER`, `EXT_PAN_ID`, and the two sleep timers when the run is too short to measure them) and agrees between header and serial; `unverified` is a value the sniffer should have seen but did not within the time, with the reason. A fox built from another conference header FAILs its `MAC_ADDR` row with a note saying so, and a fox that halted on a fatal code (a readback that differs from its header, a radio that would not start) gets the note `the fox refused to run: <the line it printed>` and nothing is listened for; both exit 1. A device that is not a fox, a fox built for another project, a missing tool or a missing privilege is said in plain words and the exit status is 2. Without a sniffer the run is serial-only and says so.

`TIME_TO_WAKE` and `TIME_TO_SLEEP` are measured on the air when `--timeout` is at least `TIME_TO_WAKE + TIME_TO_SLEEP + 5` seconds, the 5 being the boot allowance, the time a fox may take from a reset to its first frame. The sniffer then keeps listening through the fox's first sleep until it hears the fox again, and the rows read `on the air 15.0 s` (first to last frame of the first wake) and `off the air 5.0 s` (last frame of the first wake to the first of the second). `TIME_TO_WAKE` passes when the fox was on the air for `TIME_TO_WAKE` seconds, allowing the radio's spacing between frames below and the boot allowance above; `TIME_TO_SLEEP` passes when one cycle, first frame to first frame, is `TIME_TO_WAKE + TIME_TO_SLEEP` within 1 s or one percent, and the gap is at most `TIME_TO_SLEEP` plus the allowance plus that spacing, so a `TIME_TO_SLEEP 0` fox passes when it reboots in under 5 s. The end of the first wake is the fox's `Going to sleep` line, or its serial device disappearing, which a native USB board's does in deep sleep; a fox that picks its channel at random (`CHANNEL 0`) has its wake 2 channel read from serial and the sniffer retuned to it. A wake 2 the sniffer does not hear is a `FAIL` of the `TIME_TO_SLEEP` row, with the air column saying `wake 2 not heard before the deadline`, `wake 2 not heard: its channel was not seen on serial` or `wake 2 not heard on channel 9 after retuning at +33.2 s`: a rig told the channel on serial that still cannot find the fox means a hunter with a scanner has no chance. With the default `--timeout 60` the iBeacon MEDIUM demo (5/5, 15 s needed) and the Wi-Fi EASY AP (15/5, 25 s) are measured; the Classic HARD demo (30/30) needs `--timeout 65`, the 300/0 foxes `--timeout 305`. When the budget does not fit, the two rows stay `serial only` and a note names the `--timeout` that would measure them, as in `TIME_TO_WAKE and TIME_TO_SLEEP: serial only, --timeout 60 is under the 65 s the cycle needs (TIME_TO_WAKE + TIME_TO_SLEEP + 5)`; `--no-reset` gives no instant to measure from, so the rows say `serial only: --no-reset`.

Whenever a sniffer is present and the fox was reset, the line `first transmission: 1.5 s after reset` under the table gives the time from the reset to the fox's first frame, with `, over the 5 s boot allowance` appended on a measured run whose fox took longer, which is the evidence for changing the allowance. The Bluetooth scans run from before the reset and hear the first frame; a Wi-Fi or Zigbee capture can only start once the serial readback has named the channel, so when it hears the fox at once the line reads `first transmission: by 3.1 s after reset (the sniffer started listening at 3.0 s; the radio was up at 1.4 s by serial)`, the last figure being the banner's arrival, which the fox prints once its radio is up, and the timer rules allow for the part of the first wake that went unheard. The `TXPOWER` row's air column shows the median RSSI of every frame heard from the fox, `median -42 dBm over 148 frames`; the verdict stays `serial only`, since a signal strength at an unknown distance does not confirm a transmit power. The Zigbee `EXT_PAN_ID` row says why it is serial only: the extended PAN ID travels only in beacons, which a coordinator sends in reply to a beacon request, and the nRF sniffer firmware (`channel`, `receive`, `sleep`) cannot transmit one. The Wi-Fi EASY AP demo, when everything agrees:
```
Fox: wifi_ap_client EASY AP
value         | header                     | serial                     | air                            | verdict
MAC_ADDR      | F2:F4:90:22:0D:0F          | F2:F4:90:22:0D:0F          | F2:F4:90:22:0D:0F              | pass
CHANNEL       | 1                          | 1                          | 1                              | pass
FSSID         | Demo Hiro WiFi AP Easy Fox | Demo Hiro WiFi AP Easy Fox | Demo Hiro WiFi AP Easy Fox     | pass
SSID_HIDDEN   | 0                          | 0                          | 0                              | pass
SECURITY      | WPA2-PSK/CCMP              | -                          | WPA2-PSK/CCMP                  | pass
PSK           | 0123456789                 | 0123456789                 | -                              | serial only
MAX_CLIENTS   | 1                          | 1                          | -                              | serial only
TIME_TO_WAKE  | 15                         | 15                         | on the air 13.4 s              | pass
TIME_TO_SLEEP | 5                          | 5                          | off the air 5.0 s              | pass
TXPOWER       | WIFI_POWER_17dBm           | WIFI_POWER_17dBm           | median -42 dBm over 133 frames | serial only
first transmission: by 3.1 s after reset (the sniffer started listening at 3.0 s; the radio was up at 1.4 s by serial)
pass: 7 pass, 0 FAIL, 3 serial only, 0 unverified, NN s of 60 s
```
The Classic HARD demo at the default `--timeout 60`:
```
Fox: classic_discoverable HARD
value         | header                 | serial                 | air                    | verdict
MAC_ADDR      | F2:F6:6D:BC:2A:80      | F2:F6:6D:BC:2A:80      | F2:F6:6D:BC:2A:80      | pass
NAME          | Demo Case BTC Hard Fox | Demo Case BTC Hard Fox | Demo Case BTC Hard Fox | pass
TIME_TO_WAKE  | 30                     | 30                     | -                      | serial only
TIME_TO_SLEEP | 30                     | 30                     | -                      | serial only
first transmission: 2.1 s after reset
note: TIME_TO_WAKE and TIME_TO_SLEEP: serial only, --timeout 60 is under the 65 s the cycle needs (TIME_TO_WAKE + TIME_TO_SLEEP + 5)
pass: 2 pass, 0 FAIL, 2 serial only, 0 unverified, NN s of 60 s
```

What each fox needs on the air, and the privilege for it:
- Bluetooth Classic: `btmgmt` (bluez) runs an inquiry on `hci0`; needs root or `CAP_NET_ADMIN`.
- iBeacon: an active BLE scan with [bleak](https://github.com/hbldh/bleak) on `hci0`; no root needed.
- Wi-Fi: `tshark`, `iw` and `ip` put the named card into monitor mode and read beacons (AP) or probe requests (client); needs root. The card's type and state are put back when the script ends, including on Ctrl-C.
- Zigbee: an nRF52840 dongle running Nordic's 802.15.4 sniffer firmware (the one Kismet uses) and `tshark`; no root needed, only access to the dongle's serial port. `PACKET_INTERVAL` needs two Link Status frames, so an interval above about 20 seconds cannot be confirmed within the 60 second limit and is reported `unverified`. The dongle only receives, which is why `EXT_PAN_ID` stays serial only.

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

`flash_verify`, next to `verify` in every project, builds one environment of the project's `platformio.ini`, uploads it to the fox and then runs `verify`. The environment comes first; everything after it goes to `verify` unchanged, so a `--timeout` long enough for one cycle plus the 5 s boot allowance makes `verify` measure `TIME_TO_WAKE` and `TIME_TO_SLEEP` on the air after the flash:
```
cd bluetooth/classic_discoverable && ./flash_verify m5atom-hard hci0 --timeout 65
cd bluetooth/iBeacon && ./flash_verify m5atom-medium
cd wifi/wifi_ap_client && ./flash_verify m5atom-easy-ap wlan1
cd zigbee/zigbee_coordinator && ./flash_verify seeed-xiao-esp32c5-easy-coordinator -v
```
Run it as yourself, never under `sudo`: PlatformIO would leave root-owned files in `~/.platformio` and the project's `.pio/`, so the script refuses to run as root. When `verify` needs root for the devices given (Classic with an adapter, Wi-Fi with an interface) the script asks for the `sudo` password before the build and runs only the `verify` step through `sudo`. The fox's serial port is autodetected with the rules above unless given, and is the upload port; a native USB board that comes back under another name after the flash is found again. The tool checks `verify` would make run before the build, so a missing `tshark` is said before a minute of compiling; an unknown environment exits 2 with the list of the project's environments. Before the build one line names the project, the environment and the conference `src/current_conf.h` points at, which is the moment to Ctrl-C if it is the wrong one.

The moment the fox's port appears, before the tool checks and the build, `flash_verify` puts the chip into the ROM download bootloader and confirms it is there (the ROM's `waiting for download`), so a fox that wakes for only a few seconds between deep sleeps is caught on its first wake and held for the minute the build takes instead of sleeping again before the upload runs. It uses esptool's own reset: the EN/IO0 pulse for an M5 Atom's UART bridge, the USB-Serial-JTAG sequence for an AtomS3, StampS3 or XIAO ESP32-C5. On every board the LED goes dark in the bootloader and lights again when the new firmware runs after the upload. If the chip cannot be held (an unknown adapter, or no `waiting for download`) the line `could not put the fox into the bootloader, flashing the old way` is printed and the old flow continues. If anything stops the run before the upload (a failed check, a refused `sudo`, a failed build, Ctrl-C) the fox is reset back into its old firmware first, so it is never left stranded in the bootloader. The **Arduino Nano ESP32** is the exception: `pio run -t upload` flashes it with dfu-util through the DFU interface of its *running* application, not through the ROM bootloader, so there is nothing to hold; the script says so and the sleeping-fox problem remains for that board, which has to be reached while it is awake.

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

Every block of every project has `TIME_TO_WAKE`, the seconds the fox is on the air, and `TIME_TO_SLEEP`, the seconds it is off the air. One cycle, wake-up to wake-up, is exactly `TIME_TO_WAKE + TIME_TO_SLEEP`: the fox stamps the start of each cycle in RTC memory and shortens its sleep by the time its boot and checks took, and after a timer wake-up it prints `Last cycle: 60.0s, target 60s` so the serial output shows whether it kept up. A fox whose boot and checks ran past the end of a non-zero `TIME_TO_SLEEP` prints `Cycle behind by 1.3s, rebooting at once` and starts the next cycle from that moment. `TIME_TO_SLEEP 0` reboots as soon as the wake is over, which reruns the start-up checks every cycle; such a fox prints no `Cycle behind` line. `TIME_TO_WAKE` is 1-2147483 and `TIME_TO_SLEEP` 0-2147 seconds (`include/rfhssleeptimers.h`); Bluetooth Classic needs at least 15 seconds awake so an inquiry can reach it, and iBeacon at least 5, below.

The iBeacon fox's on-air window, its sleep and its advertising power are conference values too: `TIME_TO_WAKE`, `TIME_TO_SLEEP` and `TXPOWER` (an `ESP_PWR_LVL_*` name, `ESP_PWR_LVL_N12` to `ESP_PWR_LVL_P9`) in every block. `TIME_TO_WAKE` must be at least 5 seconds because the name only travels in the scan response: an active scan has to hear an advertisement and then ask for the name, and a shorter window lets a scan miss the fox or see it without its name.

### The shared skeleton

Every `src/main.cpp` is the same twelve lines apart from two strings, the project's directory name and its radio's name. `include/rfhsfox.h` owns everything a fox does that is not its radio: `rfhsboot()` (serial, the boot LED, `Initializing...`, the boot timer, `Setting up <radio>...`), `rfhsmacset()` (`MAC address set successfully` or `Error setting MAC address`), `rfhsawake()` (`Awake and screaming`, then the wake), `rfhssleep()` (`Going to sleep`, the sleep LED and the deep sleep that keeps the cycle exact) and `rfhsfatal()` (the halt described under "The LED"). The radio header that `main.cpp` includes after it provides three functions and one colour:

- `bool rfhsstartradio()` sets the MAC address through `rfhsmacset()` and starts the radio, and returns false when any step is refused.
- `bool rfhscheckradio()` prints every value read back from the stack, the device address first, with the helpers in `include/rfhsconfcheck.h`, and returns false when one differs from the conference header.
- `void rfhsstopradio()` takes the radio off the air.
- `RFHS_AWAKE_COLOR` is the colour the LED shows while the radio is on.

```cpp
#include <Arduino.h>
#include "current_conf.h"
#define RFHS_PROJECT "classic_discoverable"
#include <rfhsfox.h>
#include <rfhsclassicdiscoverable.h>

void setup() {
  rfhsboot("Bluetooth Classic");
  rfhsled(RFHS_LED_AWAKE);
  if (!rfhsstartradio()) {
    rfhsfatal(RFHS_FATAL_RADIO);
  }
  RFHS_BANNER();
  rfhsprintsleeptimers();
  if (!rfhscheckradio()) {
    rfhsfatal(RFHS_FATAL_READBACK);
  }
  rfhsawake(TIME_TO_WAKE);
  rfhsstopradio();
  rfhssleep(TIME_TO_SLEEP);
}

void loop() {
  rfhsfatal(RFHS_FATAL_LOOP);
}
```

The awake LED is set immediately before `rfhsstartradio()`, so the LED changing is the radio being switched on. The banner `Fox: <project> <DIFFICULTY> [<MODE>]` goes out once the radio is up, because a native USB board re-enumerates after deep sleep and the time the radio takes to start is what lets the host reopen the port first; the two timers and the readback lines follow it. A fox that fails before the banner prints it from `rfhsfatal()`, so `verify` reports a fox that halted rather than a device that is not a fox.

### The LED

| State | Atom, AtomS3, StampS3 (WS2812) and Nano ESP32 (RGB LED) | XIAO ESP32-C5 (one LED) | From | Until |
|---|---|---|---|---|
| boot | dark violet, `0x9400D3` | off | the first lines of `setup()` | `rfhsstartradio()` is called |
| awake | the radio's colour: Bluetooth Classic deep blue `0x0000FF`, iBeacon light blue `0x60A0FF`, Wi-Fi AP green `0x00FF00`, Wi-Fi client orange `0xFF8C00`, Zigbee cyan `0x00FFFF` | on | immediately before `rfhsstartradio()` | `Going to sleep` |
| asleep | red, `0xFF0000`, through deep sleep: the WS2812 keeps its last colour while it has power and the chip holds the Nano's three pins | off, the chip holds the pin | `Going to sleep` | the next boot |
| fatal | red blinks, as many as the code, 250 ms on and 250 ms off, then 1.5 s dark, forever | the same blinks | `PANIC` | power off |

Brightness is 20 on the WS2812 boards, M5Stack's limit for the cover over the LED. The fatal codes, each printed as `Fatal <code>: <reason>` before `PANIC`, after the radio has been stopped so a halted fox never transmits:

| Code | Reason | What happened |
|---|---|---|
| 1 | `radio start failed` | `rfhsstartradio()` returned false: the MAC address set was refused, or the stack would not start (`SerialBT.begin()`, `softAP()` or `begin()`, the Wi-Fi country code or `setTxPower()`, `Zigbee.begin()` or the link status period) |
| 2 | `readback mismatch` | `rfhscheckradio()` read back a value that differs from the conference header |
| 3 | `deep sleep returned` | `esp_deep_sleep()` came back instead of resetting the chip |
| 4 | `loop() reached` | `loop()` ran; `setup()` always ends in deep sleep |

To watch each code on a board, build with the test hook, which halts with that code right after the banner and is otherwise compiled out:
```
cd bluetooth/classic_discoverable && PLATFORMIO_BUILD_FLAGS='-D RFHS_TEST_FATAL=2' pio run -e m5atom-hard -t upload
```
No `platformio.ini` sets it; `./qa/guard-test` builds one environment with it so the hook keeps compiling.

### Conferences and reports

`./make_conference_full <name>` runs each project's `make_conference`, which copies `9999skel.h` to `<year><name>.h` with fresh identifiers (MAC addresses, iBeacon UUIDs, Zigbee PAN IDs) and, for every Wi-Fi block, a random WPA2 passphrase of 63 letters and digits, points every `current_conf.h` at the new header and then runs `./create_report <year><name>`, which writes `<year><name>.txt`, the report handed to foxes and hunters. `./switch_conference <year><name>` repoints the symlinks later. Reports are gitignored because they hold the flags; don't commit one, and `./create_report` refuses to overwrite one that exists for the same reason, so remove the old report before making it again.

The report is made by grepping the conference headers for `RFHS_CHALLENGE_NAME`, `FOX_KEYWORDS`, `NAME`, `UUID`, `MAC_ADDR`, `FSSID`, `CHANNEL` and `PAN_ID`. **Every line containing one of those words lands in the report, comments included.** Keep them out of comments in conference headers, apart from the intended `// RFHS_CHALLENGE_NAME` and `// FOX_KEYWORDS` lines. `./qa/report-format` catches a leak.

The flags come from `threewords`, which reads `/usr/share/dict/cracklib-words`. Debian and Ubuntu ship that list as `cracklib-small`; `qa/setup` adds the symlink. `dos2unix` and `uuidgen` (package `uuid-runtime` on Debian and Ubuntu) are needed too. Rolling a conference on a machine missing any of these leaves empty flags or UUIDs in the report; `./qa/report-format` catches both.

### Adding a tunable

1. Define it in every difficulty block of `9999skel.h` and `9999demo.h`, with a comment giving the range, what any special value means, and what a hunter will see change.
2. In the shared header for the challenge: refuse bad values at compile time with `#error` (numbers) or `static_assert` (strings and byte arrays, helpers in `include/rfhsconfcheck.h`), apply the value in `rfhsstartradio()`, then read it back in `rfhscheckradio()` with one of the readback helpers in `include/rfhsconfcheck.h` (`rfhscheckint`, `rfhscheckhex16`, `rfhscheckstr`, `rfhscheckbytes`; each prints `<label>: <value>` and, on a mismatch, `Requested <thing>: <value>` and `<label> != Requested <thing>`) and return false, so the fox halts on fatal code 2 instead of transmitting something other than what the report says. `CHANNEL` and `PAN_ID` in `include/rfhszigbee.h` show the pattern. The message names the variable and the permitted values, and the comment on the define in the conference header says the same thing.
3. Add a case to `qa/guard-test` for each way the value can be wrong, and run it.
4. If it should be different for every fox at every conference, give it a placeholder value in the skel and a `sed` in that project's `make_conference`. The randomizer must never produce a placeholder value, or a later `sed` replaces it again.
5. If hunters need it, add it to the grep in `create_report`, and a line pattern plus field name in `qa/verify-report`.
6. Give the readback line a regex in `foxverify/serial_fox.py`, add it to the transcripts under `foxverify/tests/fixtures/transcripts/`, and add its row to the project's run in `foxverify/run.py`, so `verify` checks it too.
7. Build every environment of the project with `./qa/build-test <project>` and run `./qa/report-format` and `./qa/verify-test`.

### Adding a board

- Add a board section to the project's `platformio.ini` with an explicit `platform = ${platform.<name>}` and name its environments `<board>-<difficulty>[-<mode>]`. CI builds its matrix from the `board` of every environment, so a new board gets its own job without touching the workflow.
- Add the LED data pin to `include/rfhsledmacros.h`; a board without one does not compile.
- Add a row to the hardware table above.

### Platforms

Platforms are pinned in each `platformio.ini` and every board section names one. `espressif32@~6.7.0` is used for all boards except the ESP32-C5, which needs the pinned pioarduino release because nothing else supports it. The Bluetooth Classic challenge needs the Bluedroid stack from Arduino core 2.x, so don't move the espressif32 pin without checking it. Never use pioarduino's `stable` download URL, its contents change. Bump a pin on purpose, in its own PR, and build everything.

### Shell scripts

A script with `#!/bin/sh` has to work in bash, dash, mksh and busybox ash, so it is POSIX sh only. A script with `#!/bin/bash` has to work in at least bash, and is only worth it when bash makes it clearly more readable; every script here is `/bin/sh`. Everything passes `shellcheck`. `./qa/shell-lint` checks all of that for every script in the repo and CI runs it on each PR. Remember that `sed`'s `e` flag, `system()` and `sh -c` run `/bin/sh` no matter what shebang your script has, so a bash function is invisible to them.

### Testing

CI builds every environment of every project twice, once with the checked in `9999demo` conference and once with a conference freshly rolled off `9999skel`, and checks the generated conference reports line by line. Before the builds it checks every `platformio.ini`: a value in a custom section must be interpolated or inherited by an environment, and every environment's platform must be pinned. After each build it checks the partition table for what the firmware needs at run time (the Zigbee stack aborts at boot without `zb_storage`); a clean build proves neither. Each project and board pair is its own job so a failure names the board that broke; a board with many environments is split by mode (`ap`, `client`) so one job doesn't set the pace. The same scripts run at home:
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
