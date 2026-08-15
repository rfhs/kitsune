// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

//WIFI_POWER_19_5dBm 78
//WIFI_POWER_19dBm 76
//WIFI_POWER_18_5dBm 74
//WIFI_POWER_17dBm 68
//WIFI_POWER_15dBm 60
//WIFI_POWER_13dBm 52
//WIFI_POWER_11dBm 44
//WIFI_POWER_8_5dBm 34
//WIFI_POWER_7dBm 28
//WIFI_POWER_5dBm 20
//WIFI_POWER_2dBm 8
//WIFI_POWER_MINUS_1dBm -4

#if defined(AP)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "WiFi AP Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi AP Easy Fox?'"
// Network config
#define FSSID "Hiro WiFi AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x6C, 0xFC, 0xFB, 0x6A, 0x3E}
// 1-13 permitted 0 means random
#define CHANNEL 1
// 0 broadcast 1 hidden
#define SSID_HIDDEN  0
// 1-4 permitted
#define MAX_CLIENTS 1
#define TIME_TO_WAKE 15
#define TIME_TO_SLEEP 5
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "WiFi AP Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi AP Hard Fox?'"
// Network config
#define FSSID "YT WiFi AP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0xC8, 0x7F, 0xC2, 0x94, 0xC4}
// 1-13 permitted 0 means random
#define CHANNEL 0
// 0 broadcast 1 hidden
#define SSID_HIDDEN 0
// 1-4 permitted
#define MAX_CLIENTS 1
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 30
#define TIME_TO_SLEEP 45
#define TXPOWER WIFI_POWER_7dBm
#endif

#if defined(FIVEEASY)
// RFHS_CHALLENGE_NAME "WiFi 5GHz AP Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi 5GHz AP Easy Fox?'"
// Network config
#define FSSID "Enzo WiFi 5GHz AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x2A, 0x71, 0xDA, 0x5D, 0xE3}
// 1-13 permitted 0 means random
#define CHANNEL 36
// 0 broadcast 1 hidden
#define SSID_HIDDEN  0
// 1-4 permitted
#define MAX_CLIENTS 1
#define TIME_TO_WAKE 15
#define TIME_TO_SLEEP 5
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(FIVEHARD)
// RFHS_CHALLENGE_NAME "WiFi 5GHz AP Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi 5GHz AP Hard Fox?'"
// Network config
#define FSSID "Lagos WiFi 5GHz AP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x47, 0x63, 0xB5, 0x2F, 0x37}
// 1-13 permitted 0 means random
#define CHANNEL 0
// 0 broadcast 1 hidden
#define SSID_HIDDEN 0
// 1-4 permitted
#define MAX_CLIENTS 1
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 30
#define TIME_TO_SLEEP 45
#define TXPOWER WIFI_POWER_7dBm
#endif
#endif

#if defined(CLIENT)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "WiFi Client Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi Client Easy Fox?'"
// set mac address
#define FSSID "Ng WiFi Client Easy Fox"
#define PSK "0123456789"
#define MAC_ADDR {0xF2, 0xD0, 0xC7, 0x3F, 0x63, 0xBC}
// Network config
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "WiFi Client Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi Client Hard Fox?'"
// Network config
#define FSSID "Mr Lee WiFi Client Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x47, 0x85, 0x78, 0x2B, 0x96}
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 0
#define TXPOWER WIFI_POWER_17dBm
#endif
#endif
