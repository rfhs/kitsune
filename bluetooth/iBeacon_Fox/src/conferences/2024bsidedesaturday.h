// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Bash to generate UUID
// uuidgen | tr '[[:lower:]]' '[[:upper:]]'

#if defined(EASY)
#define DEVICE_NAME         "Kali BLE Easy Fox"
#define BEACON_UUID         "AEE2EACB-4A3E-485B-B554-0D7FF9CC0096"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xC7, 0x9B, 0x2F, 0x55, 0xE2}

#elif defined(MEDIUM)
#define DEVICE_NAME         "Apophis BLE Medium Fox"
#define BEACON_UUID         "05B9744D-9963-4149-9032-E6B2ADCA0BAB"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xC3, 0xEB, 0x2B, 0x3D, 0x05}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "Anubis BLE Hard Fox"
#define BEACON_UUID         "E7D0633A-63BD-46CC-925D-31A0FB6D01C8"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x73, 0xF5, 0xA3, 0x34, 0x63}

#endif
