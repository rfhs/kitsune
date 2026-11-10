#if defined(EASY)
#define DEVICE_NAME         "Skye BLE Easy Fox"
#define BEACON_UUID         "27C017AC-9DCE-45E2-A538-E50C47B952A3"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xD7, 0x6B, 0xB2, 0x39, 0x42}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Rocky BLE Medium Fox"
#define BEACON_UUID         "B835176E-5BE8-4772-8C6B-AD6E63D44C07"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x8B, 0x54, 0xEF, 0x9E, 0x0B}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
#define DEVICE_NAME         "Rubble BLE Hard Fox"
#define BEACON_UUID         "6A6E45C3-EB5C-4511-B352-D51B99672B11"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xCC, 0xF3, 0x81, 0x27, 0xFA}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
