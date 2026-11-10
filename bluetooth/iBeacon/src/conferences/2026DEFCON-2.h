#if defined(EASY)
// RFHS_CHALLENGE_NAME "BLE Easy Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Easy Fox?'"
#define DEVICE_NAME         "Bruce BLE Easy Fox"
#define BEACON_UUID         "4F3235EF-BD0D-4F60-99F3-379FFAE2906A"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x34, 0x5C, 0x9C, 0xE8, 0xCD}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
// RFHS_CHALLENGE_NAME "BLE Medium Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Medium Fox?'"
#define DEVICE_NAME         "Cath BLE Medium Fox"
#define BEACON_UUID         "8DA8BE9E-7E17-4CDE-BD99-2728A63EDB4D"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xA8, 0x1D, 0x1C, 0x5E, 0x7D}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(HARD)
// RFHS_CHALLENGE_NAME "BLE Hard Fox"
// FOX_KEYWORDS        "Hunter should ask 'Are you the BLE Hard Fox?'"
#define DEVICE_NAME         "3Jane BLE Hard Fox"
#define BEACON_UUID         "4383AC60-0AA3-41B9-BF1A-08198E849B99"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x9C, 0x48, 0xAB, 0x96, 0x9A}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
