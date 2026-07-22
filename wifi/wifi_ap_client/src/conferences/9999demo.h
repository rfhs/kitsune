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
#define FSSID "Demo Hiro WiFi AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0xF4, 0x90, 0x22, 0x0D, 0x0F}
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
#define FSSID "Demo YT WiFi AP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x72, 0xC1, 0x79, 0x16, 0x1B}
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
#define FSSID "Demo Enzo WiFi 5GHz AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x77, 0x20, 0x34, 0x0A, 0xC7}
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
#define FSSID "Demo Lagos WiFi 5GHzAP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x13, 0xD4, 0x3C, 0x51, 0x4B}
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
#define FSSID "Demo Ng WiFi Client Easy Fox"
#define PSK "0123456789"
#define MAC_ADDR {0xF2, 0x44, 0x5E, 0x10, 0x97, 0xF4}
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
#define FSSID "Demo Mr Lee WiFi Client Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x83, 0x27, 0x31, 0x80, 0xC7}
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 0
#define TXPOWER WIFI_POWER_17dBm
#endif
#endif
