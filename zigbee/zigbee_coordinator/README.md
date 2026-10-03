# Zigbee Coordinator Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 with an 802.15.4 radio to enable creation of a Zigbee Coordinator fox.

Difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment                          Group     Name         Title                        Description
-----------------------------------  --------  -----------  ---------------------------  ----------------------
seeed-xiao-esp32c5-easy-coordinator  Platform  upload       Upload
seeed-xiao-esp32c5-hard-coordinator  Platform  upload       Upload
```

|Hardware |Coordinator |Serial console during sleep |
|------------------- | :---------: | :---------------------------: |
|Seeed Xiao ESP32C5 |✅|❌|

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/defcon31.h](./src/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy-coordinator, hard-coordinator]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e BOARDNAME-easy-coordinator --target upload`
- **Note:** To build without upload execute `platformio run -e BOARDNAME-easy-coordinator`
