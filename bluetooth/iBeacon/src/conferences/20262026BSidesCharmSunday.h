#if defined(EASY)
#define DEVICE_NAME         "Skye BLE Easy Fox"
#define BEACON_UUID         "E78279D8-3DB7-4474-B3CA-B2C0AD49BECF"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x99, 0x51, 0xBA, 0x71, 0xFC}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Rocky BLE Medium Fox"
#define BEACON_UUID         "2342299A-B5CD-4272-AFC8-8FD62A12119B"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x09, 0x3C, 0xE3, 0xA0, 0xDA}

#elif defined(HARD)
#define DEVICE_NAME         "Rubble BLE Hard Fox"
#define BEACON_UUID         "5EFEBB4E-08DB-4666-8818-F6D5BACBDB7A"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x00, 0x92, 0x49, 0x80, 0x35}

#endif
