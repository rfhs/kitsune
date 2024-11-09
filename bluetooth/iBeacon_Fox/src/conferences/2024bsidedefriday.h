// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Bash to generate UUID
// uuidgen | tr '[[:lower:]]' '[[:upper:]]'

#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Fox"
#define BEACON_UUID         "BC81B71B-CB76-4048-B592-2E4BC6EF505D"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xFB, 0x13, 0xA9, 0x3A, 0x87}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Fox"
#define BEACON_UUID         "A4F9958F-EA5D-40FF-8046-4D2459E7B2B9"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x88, 0xF9, 0x9E, 0x80, 0xBF}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "Anubis BLE Hard Fox"
#define BEACON_UUID         "0B5CEAA1-1991-4A47-8C88-3F85D98B8F31"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xCF, 0x16, 0x41, 0x3C, 0x4B}

#endif
