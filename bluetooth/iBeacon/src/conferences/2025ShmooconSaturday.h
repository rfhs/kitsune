#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Fox"
#define BEACON_UUID         "BCD8E52D-677A-40BC-BB4C-61A83F664FC6"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xFB, 0xD2, 0x24, 0x22, 0xCB}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Fox"
#define BEACON_UUID         "F736294C-23EA-4808-B726-DA723873C4EE"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x39, 0x0C, 0x00, 0x92, 0x14}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
#define DEVICE_NAME         "Anubis BLE Hard Fox"
#define BEACON_UUID         "F9C77D88-25D9-44C1-B83A-7091D7179F67"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xCE, 0xA9, 0x61, 0xC7, 0xDF}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
