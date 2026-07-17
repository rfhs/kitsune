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
#define RFHS_CHALLENGE_NAME "WiFi AP Easy Fox"
// Network config
#define FSSID "Zuma WiFi AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x86, 0x9C, 0x93, 0x37, 0x38}
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
#define RFHS_CHALLENGE_NAME "WiFi AP Hard Fox"
// Network config
#define FSSID "Everest WiFi AP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0xCA, 0xCF, 0x0A, 0x6B, 0x4C}
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
#define RFHS_CHALLENGE_NAME "WiFi 5GHz AP Easy Fox"
// Network config
#define FSSID "Rex WiFi 5GHz AP Easy Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0x8B, 0x0A, 0x96, 0x8A, 0xA8}
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
#define RFHS_CHALLENGE_NAME "WiFi 5GHz AP Hard Fox"
// Network config
#define FSSID "Liberty WiFi 5GHz AP Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0xB4, 0x21, 0x54, 0x87, 0x8E}
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
#define RFHS_CHALLENGE_NAME "WiFi Client Easy Fox"
// set mac address
#define FSSID "Tracker WiFi Client Easy Fox"
#define PSK "0123456789"
#define MAC_ADDR {0xF2, 0x76, 0x99, 0x05, 0x5A, 0x0C}
// Network config
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
#define RFHS_CHALLENGE_NAME "WiFi Client Hard Fox"
// Network config
#define FSSID "Robo-Dog WiFi Client Hard Fox"
#define PSK "0123456789"
// set mac address
#define MAC_ADDR {0xF2, 0xFD, 0xAD, 0x2B, 0x9F, 0xDE}
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 0
#define TXPOWER WIFI_POWER_17dBm
#endif
#endif
