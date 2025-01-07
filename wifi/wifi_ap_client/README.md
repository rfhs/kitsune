# 2.4 GHz WiFi AP or Client Fox
This is a [PlatformIO](https://platformio.org/) project to run on an ESP32 to enable creation of a 2.4 GHz WiFi AP or Client fox. 

Difficulty levels are defined as PlatformIO Environments:
```bash
$ platformio run --list-targets
Environment    Group     Name         Title                        Description
-------------  --------  -----------  ---------------------------  ----------------------
m5atom-easy-ap         Platform  buildfs      Build Filesystem Image
m5atom-easy-ap         Platform  erase        Erase Flash
m5atom-easy-ap         Platform  size         Program Size                 Calculate program size
m5atom-easy-ap         Platform  upload       Upload
m5atom-easy-ap         Platform  uploadfs     Upload Filesystem Image
m5atom-easy-ap         Platform  uploadfsota  Upload Filesystem Image OTA
m5atom-easy-client     Platform  buildfs      Build Filesystem Image
m5atom-easy-client     Platform  erase        Erase Flash
m5atom-easy-client     Platform  size         Program Size                 Calculate program size
m5atom-easy-client     Platform  upload       Upload
m5atom-easy-client     Platform  uploadfs     Upload Filesystem Image
m5atom-easy-client     Platform  uploadfsota  Upload Filesystem Image OTA
m5atom-hard-ap         Platform  buildfs      Build Filesystem Image
m5atom-hard-ap         Platform  erase        Erase Flash
m5atom-hard-ap         Platform  size         Program Size                 Calculate program size
m5atom-hard-ap         Platform  upload       Upload
m5atom-hard-ap         Platform  uploadfs     Upload Filesystem Image
m5atom-hard-ap         Platform  uploadfsota  Upload Filesystem Image OTA
m5atom-hard-client     Platform  buildfs      Build Filesystem Image
m5atom-hard-client     Platform  erase        Erase Flash
m5atom-hard-client     Platform  size         Program Size                 Calculate program size
m5atom-hard-client     Platform  upload       Upload
m5atom-hard-client     Platform  uploadfs     Upload Filesystem Image
m5atom-hard-client     Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-easy-ap       Platform  buildfs      Build Filesystem Image
m5atoms3-easy-ap       Platform  erase        Erase Flash
m5atoms3-easy-ap       Platform  size         Program Size                 Calculate program size
m5atoms3-easy-ap       Platform  upload       Upload
m5atoms3-easy-ap       Platform  uploadfs     Upload Filesystem Image
m5atoms3-easy-ap       Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-easy-client   Platform  buildfs      Build Filesystem Image
m5atoms3-easy-client   Platform  erase        Erase Flash
m5atoms3-easy-client   Platform  size         Program Size                 Calculate program size
m5atoms3-easy-client   Platform  upload       Upload
m5atoms3-easy-client   Platform  uploadfs     Upload Filesystem Image
m5atoms3-easy-client   Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-hard-ap       Platform  buildfs      Build Filesystem Image
m5atoms3-hard-ap       Platform  erase        Erase Flash
m5atoms3-hard-ap       Platform  size         Program Size                 Calculate program size
m5atoms3-hard-ap       Platform  upload       Upload
m5atoms3-hard-ap       Platform  uploadfs     Upload Filesystem Image
m5atoms3-hard-ap       Platform  uploadfsota  Upload Filesystem Image OTA
m5atoms3-hard-client   Platform  buildfs      Build Filesystem Image
m5atoms3-hard-client   Platform  erase        Erase Flash
m5atoms3-hard-client   Platform  size         Program Size                 Calculate program size
m5atoms3-hard-client   Platform  upload       Upload
m5atoms3-hard-client   Platform  uploadfs     Upload Filesystem Image
m5atoms3-hard-client   Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-easy-ap      Platform  buildfs      Build Filesystem Image
m5stamps3-easy-ap      Platform  erase        Erase Flash
m5stamps3-easy-ap      Platform  size         Program Size                 Calculate program size
m5stamps3-easy-ap      Platform  upload       Upload
m5stamps3-easy-ap      Platform  uploadfs     Upload Filesystem Image
m5stamps3-easy-ap      Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-easy-client  Platform  buildfs      Build Filesystem Image
m5stamps3-easy-client  Platform  erase        Erase Flash
m5stamps3-easy-client  Platform  size         Program Size                 Calculate program size
m5stamps3-easy-client  Platform  upload       Upload
m5stamps3-easy-client  Platform  uploadfs     Upload Filesystem Image
m5stamps3-easy-client  Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-hard-ap      Platform  buildfs      Build Filesystem Image
m5stamps3-hard-ap      Platform  erase        Erase Flash
m5stamps3-hard-ap      Platform  size         Program Size                 Calculate program size
m5stamps3-hard-ap      Platform  upload       Upload
m5stamps3-hard-ap      Platform  uploadfs     Upload Filesystem Image
m5stamps3-hard-ap      Platform  uploadfsota  Upload Filesystem Image OTA
m5stamps3-hard-client  Platform  buildfs      Build Filesystem Image
m5stamps3-hard-client  Platform  erase        Erase Flash
m5stamps3-hard-client  Platform  size         Program Size                 Calculate program size
m5stamps3-hard-client  Platform  upload       Upload
m5stamps3-hard-client  Platform  uploadfs     Upload Filesystem Image
m5stamps3-hard-client  Platform  uploadfsota  Upload Filesystem Image OTA
m5stickc-easy-ap       Platform  buildfs      Build Filesystem Image
m5stickc-easy-ap       Platform  erase        Erase Flash
m5stickc-easy-ap       Platform  size         Program Size                 Calculate program size
m5stickc-easy-ap       Platform  upload       Upload
m5stickc-easy-ap       Platform  uploadfs     Upload Filesystem Image
m5stickc-easy-ap       Platform  uploadfsota  Upload Filesystem Image OTA
m5stickc-easy-client   Platform  buildfs      Build Filesystem Image
m5stickc-easy-client   Platform  erase        Erase Flash
m5stickc-easy-client   Platform  size         Program Size                 Calculate program size
m5stickc-easy-client   Platform  upload       Upload
m5stickc-easy-client   Platform  uploadfs     Upload Filesystem Image
m5stickc-easy-client   Platform  uploadfsota  Upload Filesystem Image OTA
m5stickc-hard-ap       Platform  buildfs      Build Filesystem Image
m5stickc-hard-ap       Platform  erase        Erase Flash
m5stickc-hard-ap       Platform  size         Program Size                 Calculate program size
m5stickc-hard-ap       Platform  upload       Upload
m5stickc-hard-ap       Platform  uploadfs     Upload Filesystem Image
m5stickc-hard-ap       Platform  uploadfsota  Upload Filesystem Image OTA
m5stickc-hard-client   Platform  buildfs      Build Filesystem Image
m5stickc-hard-client   Platform  erase        Erase Flash
m5stickc-hard-client   Platform  size         Program Size                 Calculate program size
m5stickc-hard-client   Platform  upload       Upload
m5stickc-hard-client   Platform  uploadfs     Upload Filesystem Image
m5stickc-hard-client   Platform  uploadfsota  Upload Filesystem Image OTA
```

Only M5Atom is currently fully supported.
M5AtomS3 and M5StampS3 work except for serial output.
M5StickC works except the hardware lacks an RGB led for output.

To use:
- [Install PlatformIO](https://platformio.org/install/cli)
- Create a conference specific file header file e.g. `src/defcon31.h` and symlink it to `src/current_conf.h`
- Modify variables in your conference specific file e.g. ['src/defcon31.h](./src/defcon31.h) for each of the difficulty levels
- Select your difficulty level with the `-e` argument to `platformio run`, options are [easy_ap, hard_ap, easy_client hard_client]
- **Note:** You can specify a target device serial port with argument `--upload-port` to avoid automatic detection.
- For example, to build and upload Easy: `platformio run -e easy_ap --target upload`
- **Note:** To build without upload execute `platformio run -e easy_ap`
