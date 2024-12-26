// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Bash to generate UUID
// uuidgen | tr '[[:lower:]]' '[[:upper:]]'

#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Demo"
#define BEACON_UUID         "3BDB3CAB-CA78-48C1-9DBC-1CF8C338CA2A"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xCF, 0x52, 0xCA, 0x3E, 0xF9}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Demo"
#define BEACON_UUID         "71F24C1B-BBA4-4EB3-8D62-787A7BF440EC"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x3F, 0x21, 0xF5, 0x89, 0x58}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "Anubis BLE Hard Demo"
#define BEACON_UUID         "4A79F8EB-67C5-48EB-8587-1A659E90A0AE"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x3B, 0x4F, 0x07, 0x0B, 0xA2}

#endif
