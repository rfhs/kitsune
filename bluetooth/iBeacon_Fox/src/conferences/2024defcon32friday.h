// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Bash to generate UUID
// uuidgen | tr '[[:lower:]]' '[[:upper:]]'

#if defined(EASY)
#define DEVICE_NAME         "Kali"
#define BEACON_UUID         "68457DFE-785B-49A7-9FF5-4F3F23E9A5A6"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x16, 0xE5, 0x2B, 0xF5, 0x20}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis"
#define BEACON_UUID         "72F300AC-03B2-4FDF-AC65-BD2B6BE10D0C"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x20, 0xC4, 0x1F, 0x8E, 0x28}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "Anubis"
#define BEACON_UUID         "A7BC7470-7C08-443F-BEF6-44F15FC93447"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xE6, 0xB6, 0xC0, 0xC0, 0x2C}

#endif
