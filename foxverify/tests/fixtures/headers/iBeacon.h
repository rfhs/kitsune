// Frozen copy of bluetooth/iBeacon/src/conferences/9999demo.h for the tests. The
// transcripts under ../transcripts and the literal values in the tests match
// this copy, not the live demo header, which is rolled anew each year.

#if defined(EASY)
// RFHS_CHALLENGE_NAME "BLE Easy Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Easy Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "Demo Bruce BLE Easy Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "A2AFA582-E4E8-4599-B28B-4E11AC6DD6E8"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0xF2, 0x82, 0x42, 0xD0, 0x84, 0xBC}
// Seconds on the air, at least 5 so an active scan can hear the beacon and read its name
#define TIME_TO_WAKE        300
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP       0
// Advertising power, an ESP_PWR_LVL_* name from ESP_PWR_LVL_N12 (-12 dBm) to ESP_PWR_LVL_P9 (+9 dBm) in 3 dBm steps
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
// RFHS_CHALLENGE_NAME "BLE Medium Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Medium Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "Demo Cath BLE Medium Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "162EEB7B-743C-47E9-9414-BBD6149B4E40"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0xF2, 0x63, 0x89, 0x10, 0x8D, 0x1D}
// Seconds on the air, at least 5 so an active scan can hear the beacon and read its name
#define TIME_TO_WAKE        5
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP       5
// Advertising power, an ESP_PWR_LVL_* name from ESP_PWR_LVL_N12 (-12 dBm) to ESP_PWR_LVL_P9 (+9 dBm) in 3 dBm steps
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
// RFHS_CHALLENGE_NAME "BLE Hard Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Hard Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "Demo 3Jane BLE Hard Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "DB6A0ED0-1DC3-4348-BD78-E997A0C082A3"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0xF2, 0xAC, 0x87, 0x05, 0x0A, 0xC7}
// Seconds on the air, at least 5 so an active scan can hear the beacon and read its name
#define TIME_TO_WAKE        10
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP       30
// Advertising power, an ESP_PWR_LVL_* name from ESP_PWR_LVL_N12 (-12 dBm) to ESP_PWR_LVL_P9 (+9 dBm) in 3 dBm steps
#define TXPOWER             ESP_PWR_LVL_N12

#endif
