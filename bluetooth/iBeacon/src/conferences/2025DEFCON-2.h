#if defined(EASY)
#define DEVICE_NAME         "Skye BLE Easy Fox"
#define BEACON_UUID         "A92D4D14-AA91-4416-884E-1F57845E5885"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x97, 0xDD, 0xC8, 0x76, 0x59}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Rocky BLE Medium Fox"
#define BEACON_UUID         "D9948D8E-5B73-4649-8FDE-4961EBD94E9D"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xA0, 0x70, 0x0C, 0x9E, 0x03}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
#define DEVICE_NAME         "Rubble BLE Hard Fox"
#define BEACON_UUID         "2B70F65A-63F4-4882-9393-B3A20043F7CB"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xB5, 0xC0, 0x36, 0x48, 0xD5}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
