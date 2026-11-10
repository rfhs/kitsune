#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Fox"
#define BEACON_UUID         "16D3C34C-3110-482A-AA86-0AE177B96C90"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x73, 0xE5, 0x73, 0x5C, 0x92}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Fox"
#define BEACON_UUID         "310CD531-8EF3-40FA-B23C-2D2559091054"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xB8, 0x4C, 0xDC, 0x8D, 0x50}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
#define DEVICE_NAME         "Anubis BLE Hard Fox"
#define BEACON_UUID         "BFD321FB-659E-4A17-85FE-F697FEB44FF3"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x2D, 0x9D, 0xED, 0xD8, 0xF3}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
