# 2.4 GHz WiFi AP or Client Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of a 2.4 GHz WiFi AP or Client fox. 

Difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment    Group     Name         Title                        Description
-------------  --------  -----------  ---------------------------  ----------------------
easy_ap        Platform  buildfs      Build Filesystem Image
easy_ap        Platform  erase        Erase Flash
easy_ap        Platform  size         Program Size                 Calculate program size
easy_ap        Platform  upload       Upload
easy_ap        Platform  uploadfs     Upload Filesystem Image
easy_ap        Platform  uploadfsota  Upload Filesystem Image OTA

hard_ap        Platform  buildfs      Build Filesystem Image
hard_ap        Platform  erase        Erase Flash
hard_ap        Platform  size         Program Size                 Calculate program size
hard_ap        Platform  upload       Upload
hard_ap        Platform  uploadfs     Upload Filesystem Image
hard_ap        Platform  uploadfsota  Upload Filesystem Image OTA

easy_client    Platform  buildfs      Build Filesystem Image
easy_client    Platform  erase        Erase Flash
easy_client    Platform  size         Program Size                 Calculate program size
easy_client    Platform  upload       Upload
easy_client    Platform  uploadfs     Upload Filesystem Image
easy_client    Platform  uploadfsota  Upload Filesystem Image OTA

hard_client    Platform  buildfs      Build Filesystem Image
hard_client    Platform  erase        Erase Flash
hard_client    Platform  size         Program Size                 Calculate program size
hard_client    Platform  upload       Upload
hard_client    Platform  uploadfs     Upload Filesystem Image
hard_client    Platform  uploadfsota  Upload Filesystem Image OTA
```

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/defcon31.h](./src/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy_ap, hard_ap, easy_client hard_client]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e easy_ap --target upload`
- **Note:** To build without upload execute `platformio run -e easy_ap`
