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
// set mac address
#define MAC_ADDR {0xF2, 0xE2, 0xF5, 0x12, 0xC6, 0xC9}
// Network config
#define FSSID "Zuma WiFi AP Easy Fox Demo"
#define PSK "0123456789"
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
// set mac address
#define MAC_ADDR {0xF2, 0xA2, 0xD3, 0xD4, 0xF3, 0x40}
// Network config
#define FSSID "Everest WiFi AP Hard Fox Demo"
#define PSK "0123456789"
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
// set mac address
#define MAC_ADDR {0xF2, 0x99, 0x68, 0x88, 0x95, 0xBA}
// Network config
#define FSSID "Tracker WiFi Client Easy Fox Demo"
#define PSK "0123456789"
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
// set mac address
#define MAC_ADDR {0xF2, 0xE2, 0x63, 0xAA, 0x91, 0x6F}
// Network config
#define FSSID "Robo-Dog WiFi Client Hard Fox Demo"
#define PSK "0123456789"
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 0
#define TXPOWER WIFI_POWER_17dBm
#endif
#endif
