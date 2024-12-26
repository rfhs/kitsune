# Bluetooth Classic Discoverable Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of an iBeacon BLE fox. 

Difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment    Group     Name         Title                        Description
-------------  --------  -----------  ---------------------------  ----------------------
easy           Platform  buildfs      Build Filesystem Image
easy           Platform  erase        Erase Flash
easy           Platform  size         Program Size                 Calculate program size
easy           Platform  upload       Upload
easy           Platform  uploadfs     Upload Filesystem Image
easy           Platform  uploadfsota  Upload Filesystem Image OTA

hard           Platform  buildfs      Build Filesystem Image
hard           Platform  erase        Erase Flash
hard           Platform  size         Program Size                 Calculate program size
hard           Platform  upload       Upload
hard           Platform  uploadfs     Upload Filesystem Image
hard           Platform  uploadfsota  Upload Filesystem Image OTA
```

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/conferences/defcon31.h](./src/conferences/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy, hard]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e easy --target upload`
- **Note:** To build without upload execute `platformio run -e easy`
