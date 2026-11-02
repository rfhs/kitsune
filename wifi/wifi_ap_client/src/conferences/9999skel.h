// MAC addresses are rolled by make_conference: random, unicast and locally
// administered, so the first byte is even and ends in 2, 6, A or E.

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
// Network name, 1-32 characters
#define FSSID "Hiro WiFi AP Easy Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x01, 0x02, 0x03, 0x04, 0x05}
// 0 random every wake, or 1-11 (country US)
#define CHANNEL 1
// 0 broadcasts the SSID, 1 hides it
#define SSID_HIDDEN  0
// Stations the AP accepts, 1-10
#define MAX_CLIENTS 1
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 15
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 5
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "WiFi AP Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi AP Hard Fox?'"
// Network name, 1-32 characters
#define FSSID "YT WiFi AP Hard Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x06, 0x07, 0x08, 0x09, 0x0a}
// 0 random every wake, or 1-11 (country US)
#define CHANNEL 0
// 0 broadcasts the SSID, 1 hides it
#define SSID_HIDDEN 0
// Stations the AP accepts, 1-10
#define MAX_CLIENTS 1
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 30
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 45
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_7dBm
#endif

#if defined(FIVEEASY)
// RFHS_CHALLENGE_NAME "WiFi 5GHz AP Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi 5GHz AP Easy Fox?'"
// Network name, 1-32 characters
#define FSSID "Enzo WiFi 5GHz AP Easy Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f}
// 0 random every wake, or a non-DFS 5 GHz channel: 36 40 44 48 149 153 157 161 165
#define CHANNEL 36
// 0 broadcasts the SSID, 1 hides it
#define SSID_HIDDEN  0
// Stations the AP accepts, 1-10
#define MAX_CLIENTS 1
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 15
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 5
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(FIVEHARD)
// RFHS_CHALLENGE_NAME "WiFi 5GHz AP Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi 5GHz AP Hard Fox?'"
// Network name, 1-32 characters
#define FSSID "Lagos WiFi 5GHz AP Hard Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x10, 0x11, 0x12, 0x13, 0x14}
// 0 random every wake, or a non-DFS 5 GHz channel: 36 40 44 48 149 153 157 161 165
#define CHANNEL 0
// 0 broadcasts the SSID, 1 hides it
#define SSID_HIDDEN 0
// Stations the AP accepts, 1-10
#define MAX_CLIENTS 1
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 30
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 45
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_7dBm
#endif
#endif

#if defined(CLIENT)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "WiFi Client Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi Client Easy Fox?'"
// Network name, 1-32 characters
#define FSSID "Ng WiFi Client Easy Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x15, 0x16, 0x17, 0x18, 0x19}
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 1
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_17dBm
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "WiFi Client Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the WiFi Client Hard Fox?'"
// Network name, 1-32 characters
#define FSSID "Mr Lee WiFi Client Hard Fox"
// WPA2 passphrase, 8-63 characters
#define PSK "0123456789"
// 6 bytes, first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e}
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 0
// A WIFI_POWER_* name from the list at the top
#define TXPOWER WIFI_POWER_17dBm
#endif
#endif
