// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

#if defined(EASY)
#define DEVICE_NAME         "GhostTrap"
#define BEACON_UUID         "2D7A9F0C-E0E8-4CC9-A71B-A21DB2D034A1"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xca, 0x5c, 0x5b, 0x03, 0xcd}

#elif defined(MEDIUM)
#define DEVICE_NAME         "EctoGoggles"
#define BEACON_UUID         "ED5EABFB-BCE6-491C-A1B0-D308425099D3"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xDA, 0xAB, 0x99, 0x68, 0x3E}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "PKEMeter"
#define BEACON_UUID         "5C5EA75C-CDDF-41DB-8D6A-B1EE023084C1"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x39, 0xC7, 0xCE, 0xC5, 0xAA}

#endif
