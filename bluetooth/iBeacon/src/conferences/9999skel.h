#if defined(EASY)
// RFHS_CHALLENGE_NAME "BLE Easy Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Easy Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "Bruce BLE Easy Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "00000001-0002-0003-0004-000000000005"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0x00, 0x01, 0x02, 0x03, 0x04, 0x05}

#elif defined(MEDIUM)
// RFHS_CHALLENGE_NAME "BLE Medium Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Medium Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "Cath BLE Medium Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "00000006-0007-0008-0009-00000000000a"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0x00, 0x06, 0x07, 0x08, 0x09, 0x0a}

#elif defined(HARD)
// RFHS_CHALLENGE_NAME "BLE Hard Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Hard Fox?'"
// Name hunters see, 1-29 characters, longer is sent truncated
#define DEVICE_NAME         "3Jane BLE Hard Fox"
// 36 characters, 8-4-4-4-12 hex digits with hyphens
#define BEACON_UUID         "0000000b-000c-000d-000e-00000000000f"
// MAJOR and MINOR 0-65535
#define MAJOR               5
#define MINOR               88
// Calibrated RSSI at one metre in dBm, as a signed byte: 0xC5 is -59
#define SIGNAL_POWER        0xc5
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR            {0x00, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f}

#endif
