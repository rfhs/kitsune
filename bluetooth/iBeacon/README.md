# iBeacon BLE Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of an iBeacon BLE fox. 

Target hardware and difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment    Group     Name         Title                        Description
-------------  --------  -----------  ---------------------------  ----------------------
Environment       Group     Name         Title                        Description
m5atom-easy       Platform  buildfs      Build Filesystem Image
m5atom-easy       Platform  erase        Erase Flash
m5atom-easy       Platform  size         Program Size                 Calculate program size
m5atom-easy       Platform  upload       Upload
m5atom-easy       Platform  uploadfs     Upload Filesystem Image
m5atom-easy       Platform  uploadfsota  Upload Filesystem Image OTA
m5atom-hard       Platform  buildfs      Build Filesystem Image
m5atom-hard       Platform  erase        Erase Flash
m5atom-hard       Platform  size         Program Size                 Calculate program size
m5atom-hard       Platform  upload       Upload
m5atom-hard       Platform  uploadfs     Upload Filesystem Image
m5atom-hard       Platform  uploadfsota  Upload Filesystem Image OTA
m5atom-medium     Platform  buildfs      Build Filesystem Image
m5atom-medium     Platform  erase        Erase Flash
m5atom-medium     Platform  size         Program Size                 Calculate program size
m5atom-medium     Platform  upload       Upload
m5atom-medium     Platform  uploadfs     Upload Filesystem Image
m5atom-medium     Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-easy     Platform  buildfs      Build Filesystem Image
m5atoms3-easy     Platform  erase        Erase Flash
m5atoms3-easy     Platform  size         Program Size                 Calculate program size
m5atoms3-easy     Platform  upload       Upload
m5atoms3-easy     Platform  uploadfs     Upload Filesystem Image
m5atoms3-easy     Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-hard     Platform  buildfs      Build Filesystem Image
m5atoms3-hard     Platform  erase        Erase Flash
m5atoms3-hard     Platform  size         Program Size                 Calculate program size
m5atoms3-hard     Platform  upload       Upload
m5atoms3-hard     Platform  uploadfs     Upload Filesystem Image
m5atoms3-hard     Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-medium   Platform  buildfs      Build Filesystem Image
m5atoms3-medium   Platform  erase        Erase Flash
m5atoms3-medium   Platform  size         Program Size                 Calculate program size
m5atoms3-medium   Platform  upload       Upload
m5atoms3-medium   Platform  uploadfs     Upload Filesystem Image
m5atoms3-medium   Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-easy    Platform  buildfs      Build Filesystem Image
m5stamps3-easy    Platform  erase        Erase Flash
m5stamps3-easy    Platform  size         Program Size                 Calculate program size
m5stamps3-easy    Platform  upload       Upload
m5stamps3-easy    Platform  uploadfs     Upload Filesystem Image
m5stamps3-easy    Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-hard    Platform  buildfs      Build Filesystem Image
m5stamps3-hard    Platform  erase        Erase Flash
m5stamps3-hard    Platform  size         Program Size                 Calculate program size
m5stamps3-hard    Platform  upload       Upload
m5stamps3-hard    Platform  uploadfs     Upload Filesystem Image
m5stamps3-hard    Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-medium  Platform  buildfs      Build Filesystem Image
m5stamps3-medium  Platform  erase        Erase Flash
m5stamps3-medium  Platform  size         Program Size                 Calculate program size
m5stamps3-medium  Platform  upload       Upload
m5stamps3-medium  Platform  uploadfs     Upload Filesystem Image
m5stamps3-medium  Platform  uploadfsota  Upload Filesystem Image OTA
```

|Hardware |Supported |Correct MAC Address | Tested |Serial console during sleep |
|------------------- | :---------: | :-------------------: | :------: | :---------------------------: |
|M5Stack Atom-lite |✅|✅|✅|✅|
|M5Stack AtomS3-lite |✅|✅|❌ (-1) |❌|
|M5Stack StampS3 |✅|✅|❌|❌ (-1) |

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/conferences/defcon31.h](./src/conferences/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy, medium, hard]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e easy --target upload`
- **Note:** To build without upload execute `platformio run -e easy`
