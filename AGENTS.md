# AGENTS.md

Guidance for AI agents working in this repository. Humans: the rules in
README.md under "Working on the code" apply to everyone; this file adds
what an agent needs on top of them.

kitsune is firmware for RF CTF foxes: small ESP32 transmitters hidden at a
conference that hunters find with Kismet, a phone, or a sniffer. Every
identifier a fox transmits is printed on a paper report, so the firmware,
the conference headers and the report scripts have to agree exactly.

## Read first

- README.md, "Working on the code". Layout, conference headers, the report
  grep that leaks comment text, the tunable and board checklists, the
  platform pins.
- `include/` is shared by all four projects. A change there needs every
  project rebuilt, not just the one you were asked about.

## Build and verify

- A clean build is necessary, not sufficient. The serial readback checks
  in the shared headers (`rfhscheckzigbee()` and friends) are the test a
  tunable gets on the device: every value is read back from the stack
  after it is applied and a mismatch halts the fox on the fatal LED. Keep
  that pattern for anything you add.
- Say what you verified and how, and what you could not. Don't describe
  an untested path as working.
- `pio` must be on PATH. The pioarduino platform needs Python 3.10 or
  newer; on a machine with an older system Python use
  `uv tool install --python 3.12 platformio` or pipx.
- Build output is large. Redirect it to a file and grep for
  `[SUCCESS]` or `[FAILED]`; print one result line.
- After touching a shared header, grep the build log for warnings in it
  (`grep 'rfhszigbee.h.*warning'`). The bar is zero.
- `./qa/build-test <project> [board] [mode]` is what one CI job runs. Use
  it, or `pio run -e <env>` for a single environment while iterating.
- To test a compile-time guard, edit `9999demo.h`, build, then restore it.
  Afterwards `git status` must show only the files you meant to change.
- Confirm platform resolution after touching a `platformio.ini`:
  `pio project config --project-dir <project> --json-output` must give
  every environment an explicit pinned `platform`.
- Run `./qa/report-format` whenever a conference header, `create_report`,
  `make_conference_full`, a `make_conference` or `qa/verify-report`
  changes. Zero failures is the bar. If a failure looks like your machine's
  fault (no word list, no `uuidgen`), fix the machine or use
  `qa/in-ubuntu`; don't file the failure under "expected here". That habit
  hid a bug that blanked every flag CI ever printed.
- Every unexpected line on stderr is a bug until you have explained it. A
  `grep: No such file` scrolling past a passing run means a fox is missing
  from the report.

## Test in the runner's image, not just on your machine

The CI runner is `ubuntu-24.04`. Three things differ from most developer
machines, and each is enough to make a change pass locally and fail in CI:

- `/bin/sh` is dash. Anything that spawns a shell (`sed`'s `e` flag,
  `system()`, `sh -c`) gets no bash features and can't see functions
  exported with `export -f`.
- Only what `qa/setup` installs is there. A bare Ubuntu has no `uuidgen`
  and no `git`.
- Tools you lack locally (the cracklib word list) make you tolerate
  failures CI would never see, so the real failures hide among them.

So, before handing off any change to a script, a workflow, `qa/`, or the
report generators, run the affected check inside the image:

    ./qa/in-ubuntu                                     # qa/report-format
    ./qa/in-ubuntu ./qa/build-test <project> <board> [mode]   # the CI leg you touched

It copies the checkout into an `ubuntu:24.04` container, runs `qa/setup`
exactly as CI does, then your command. A new external command in any
script means a new package in `qa/setup` and a note in the README, in the
same change.

## Shell scripts

- Every shell script passes `shellcheck` with no findings. shellcheck
  reads the dialect from the shebang, so run it on the file, not on
  stdin. Disable a check only on the line that needs it, with a
  `# shellcheck disable=SCxxxx` comment that says why.
- A script that starts `#!/bin/sh` must work in **bash, dash, mksh and
  busybox ash**. That means POSIX sh and nothing else: no arrays, no
  `[[ ]]`, no `function`, no `${var//a/b}` or `${var^^}`, no `$'...'`,
  no `<(...)`, no `set -o pipefail`, no `echo -e` (use `printf`), no
  `source` (use `.`), and no `export -f`. Debian and Ubuntu run `/bin/sh`
  as dash, Alpine and OpenWrt as busybox ash, so a bashism that works on
  your machine breaks CI or someone's fox-flashing laptop.
- A script that starts `#!/bin/bash` must work in at least bash. Use it
  only when a bash feature makes the script clearly more readable than
  the `/bin/sh` version; don't reach for it out of habit.
- Anything that spawns a shell for you runs `/bin/sh`, whatever the
  script's own shebang: `sed`'s `e` flag, `system()`, `find -exec sh -c`,
  `xargs sh -c`, Python's `subprocess(shell=True)`. The command you hand
  it must meet the `/bin/sh` rules even from inside a bash script, and a
  bash function exported with `export -f` is invisible to it.
- `./qa/shell-lint` enforces all of the above and the Shell Scripts
  workflow runs it on every PR: it finds every script by its shebang,
  runs shellcheck on each, and parses every `#!/bin/sh` script with
  bash, dash, mksh and busybox ash. It needs those shells and the newest
  shellcheck release; `qa/setup` installs them, or run
  `./qa/in-ubuntu ./qa/shell-lint`. Run it before handing off any script.
- Every script sets `set -e` and `set -u` before doing anything. A script
  that creates conference files or moves `current_conf.h` must put
  everything back on exit, including on failure, with a `trap`.

## Conventions the owner has asked for

- Comments describe the code as it is, for someone who was not in the
  conversation: what it does and why, in complete sentences, as short as
  that allows. Never what it replaced, how it used to work, or the bug
  that led here; that belongs in the commit message. Fragments, notes to
  self and clever phrasing get sent back.
- Don't exclude a value from a range without a reason you can state. If
  the spec allows it, support it.
- 16-bit identifiers print as `0x%04X` in firmware output, in the report
  scripts and in comments, so they match what Kismet shows.
- A bare `0` means "random" for `CHANNEL` and `PAN_ID`. For `PAN_ID`,
  `0x0000` is a real PAN ID; the firmware tells the two apart by
  stringizing the macro and comparing text, because to `#if` they are the
  same number. Keep that distinction if you add similar tunables.
- MAC and extended PAN ID are written most significant byte first in the
  headers. The stack stores them least significant byte first. Reverse on
  the way in, index from the end when printing.
- Environment names are `<board>-<difficulty>[-<mode>]`. The CI matrix is
  derived from the ini files; never hand-maintain an environment list in
  YAML. A board whose job is too slow is split by trailing mode through
  the `split_by_mode` list at the top of `qa/build-test`, nothing else.
- Workflows stay thin and call a script in `qa/`, so a human can run the
  same thing at home.
- Firmware changes and CI changes go in separate commits.

## Zigbee facts that took disassembly to learn

The stack libraries are binary. These facts come from reading
`~/.platformio/packages/framework-arduinoespressif32-libs/esp32c5/lib/*.a`
with `riscv32-esp-elf-objdump -dr` and checked against the esp-zigbee-sdk
`release/v1.0` headers. Arduino core 3.3.12 ships esp-zigbee-lib 1.6.8.

- The periodic packet hunters hear from the coordinator is the NWK Link
  Status broadcast. `esp_zb_nwk_set_link_status_period()` takes seconds
  as `uint8_t`, so 1-255. Set it after `Zigbee.begin()` returns, under
  `esp_zb_lock_acquire()`.
- `esp_zb_set_pan_id()` after formation works for any value 0x0000-0xFFFE.
  Only 0xFFFF is reserved. The stack treats a PAN ID of 0 as "not set"
  only while forming the network, which we are past by then.
- A coordinator's short address is 0x0000 and cannot be changed once the
  network exists. `esp_zb_nwk_set_short_address()` in
  `test/esp_zigbee_test_utils.h` returns `ESP_ERR_INVALID_STATE` after
  join and only writes the NWK layer anyway. The short address rules for
  a future router or end device fox are in `include/rfhszigbee.h`.
- The extended PAN ID is only sent in beacons, and a coordinator only
  beacons in reply to a scan. Kismet shows it after something has scanned
  the channel; the Link Status packets don't carry it.
- Kismet names a short-addressed device `<PAN ID> / <short address>` and
  fills "IEEE address" from the MAC in the NWK header. Kismet skips
  broadcast PAN 0xFFFF and broadcast short address 0xFFFF only; PAN
  0x0000 is tracked normally.

## Before you finish

- Leave the tree clean: no `<year>qa-*.h` or test conference headers, no
  `*.txt` reports, every `current_conf.h` pointing at
  `conferences/9999demo.h`, and `git status` showing only the files you
  meant to change.
- If the report scripts or conference headers changed, show the zigbee
  lines of a generated report so the reviewer can see the format.
