// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Bash to generate UUID
// uuidgen | tr '[[:lower:]]' '[[:upper:]]'

#if defined(EASY)
#define DEVICE_NAME         "Kali"
#define BEACON_UUID         "4F9F4075-57DC-4F1D-B028-905CCDB0D344"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xFE, 0x1F, 0xCF, 0x2B, 0xD3}
#define TIME_TO_WAKE        300
#define TIME_TO_SLEEP       0
#define TXPOWER             ESP_PWR_LVL_P9

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis"
#define BEACON_UUID         "51AD602D-A475-4816-B85A-1223F1A14EA7"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x4A, 0xAA, 0x57, 0x67, 0x0D}
#define TIME_TO_WAKE        5
#define TIME_TO_SLEEP       5
#define TXPOWER             ESP_PWR_LVL_N0

#elif defined(DIFFICULT)
#define DEVICE_NAME         "Anubis"
#define BEACON_UUID         "09E88397-927B-4012-BA21-488F6BEB7B66"
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x1C, 0x75, 0xDC, 0x44, 0xBD}
#define TIME_TO_WAKE        10
#define TIME_TO_SLEEP       30
#define TXPOWER             ESP_PWR_LVL_N12

#endif
