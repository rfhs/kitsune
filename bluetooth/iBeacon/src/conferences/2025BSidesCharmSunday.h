#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Fox"
#define BEACON_UUID         "F589CEC1-7DF3-4B5C-882D-D5373BED5A05"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x7F, 0x04, 0xB6, 0x07, 0x5C}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Fox"
#define BEACON_UUID         "CD263742-7378-41CF-A058-41E4B081BE4B"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x4F, 0xFB, 0x70, 0x42, 0x1E}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
#define DEVICE_NAME         "Anubis BLE Hard Fox"
#define BEACON_UUID         "9F837180-D978-4E46-8CB3-D3AA6E722CFE"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x39, 0x54, 0x59, 0xA2, 0xCF}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
