# 2.4 GHz WiFi AP or Client Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of a 2.4 GHz WiFi AP or Client fox. 

Difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment    Group     Name         Title                        Description
-------------  --------  -----------  ---------------------------  ----------------------
arduino-nano-esp32-easy-ap      Platform  upload         Upload
arduino-nano-esp32-hard-ap      Platform  upload         Upload
m5atom-easy-ap                  Platform  upload         Upload
m5atom-easy-client              Platform  upload         Upload
m5atom-hard-ap                  Platform  upload         Upload
m5atom-hard-client              Platform  upload         Upload
m5atoms3-easy-ap                Platform  upload         Upload
m5atoms3-easy-client            Platform  upload         Upload
m5atoms3-hard-ap                Platform  upload         Upload
m5atoms3-hard-client            Platform  upload         Upload
m5stamps3-easy-ap               Platform  upload         Upload
m5stamps3-easy-client           Platform  upload         Upload
m5stamps3-hard-ap               Platform  upload         Upload
m5stamps3-hard-client           Platform  upload         Upload
seeed-xiao-esp32c5-easy-ap      Platform  upload         Upload
seeed-xiao-esp32c5-fiveeasy-ap  Platform  upload         Upload
seeed-xiao-esp32c5-fivehard-ap  Platform  upload         Upload
seeed-xiao-esp32c5-hard-ap      Platform  upload         Upload
```

|Hardware |AP |client |Serial console during sleep |
|------------------- | :---------: | :------: | :---------------------------: |
|M5Stack Atom-lite |✅|✅|✅|
|M5Stack AtomS3-lite |✅|✅|❌|
|M5Stack StampS3 |✅|✅|❌|
|Ardunio Nano ESP32 |✅|✅|❌|
|Seeed Xiao ESP32C5 |✅|✅|❌|

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/defcon31.h](./src/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy_ap, hard_ap, easy_client hard_client]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e BOARDNAME-easy-ap --target upload`
- **Note:** To build without upload execute `platformio run -e BOARDNAME-easy-ap`
