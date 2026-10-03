// Bash to generate MAC address
// Note: 802.15.4 uses an 8 byte (EUI-64) address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// TXPOWER is in dBm, -15 to 20 on the ESP32-C5

#if defined(COORDINATOR)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "Zigbee Coordinator Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Coordinator Easy Fox?'"
// set mac address
#define MAC_ADDR {0xF2, 0x5A, 0x3C, 0x91, 0x0E, 0x7B, 0x44, 0xD8}
// 11-26 permitted 0 means random
#define CHANNEL 15
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define TXPOWER 20
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "Zigbee Coordinator Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Coordinator Hard Fox?'"
// set mac address
#define MAC_ADDR {0xF2, 0xA7, 0x19, 0x62, 0xC3, 0x08, 0xBE, 0x35}
// 11-26 permitted 0 means random
#define CHANNEL 0
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 30
#define TIME_TO_SLEEP 45
#define TXPOWER -12
#endif
#endif
