#if defined(EASY)
#define DEVICE_NAME         "Skye BLE Easy Fox"
#define BEACON_UUID         "00000001-0002-0003-0004-000000000005"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0x00, 0x01, 0x02, 0x03, 0x04, 0x05}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Rocky BLE Medium Fox"
#define BEACON_UUID         "00000006-0007-0008-0009-00000000000a"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0x00, 0x06, 0x07, 0x08, 0x09, 0x0a}

#elif defined(HARD)
#define DEVICE_NAME         "Rubble BLE Hard Fox"
#define BEACON_UUID         "0000000b-000c-000d-000e-00000000000f"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0x00, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f}

#endif
