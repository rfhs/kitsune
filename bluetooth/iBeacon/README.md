# iBeacon BLE Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of an iBeacon BLE fox. 

Target hardware and difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment                Group     Name           Title
-------------------------  --------  -------------  -------------------------------------------
arduino_nano_esp32-easy    Platform  upload         Upload
arduino_nano_esp32-hard    Platform  upload         Upload
arduino_nano_esp32-medium  Platform  upload         Upload
m5atom-easy                Platform  upload         Upload
m5atom-hard                Platform  upload         Upload
m5atom-medium              Platform  upload         Upload
m5atoms3-easy              Platform  upload         Upload
m5atoms3-hard              Platform  upload         Upload
m5atoms3-medium            Platform  upload         Upload
m5stamps3-easy             Platform  upload         Upload
m5stamps3-hard             Platform  upload         Upload
m5stamps3-medium           Platform  upload         Upload
```

|Hardware |Supported |Correct MAC Address | Tested |Serial console during sleep |
| :-------------------: | :---------: | :-------------------: | :------: | :---------------------------: |
|M5Stack Atom-lite |✅|✅|✅|✅|
|M5Stack AtomS3-lite |✅|✅|✅|❌|
|M5Stack StampS3 |✅|✅|✅|❌|
|Arduino Nano ESP32 |✅|✅|✅|❌|

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/conferences/defcon31.h](./src/conferences/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy, medium, hard]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e BOARDNAME-easy --target upload`
- **Note:** To build without upload execute `platformio run -e BOARDNAME-easy`
