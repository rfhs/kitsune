// Bash to generate MAC address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

#if defined(EASY)
#define DEVICE_NAME         "GhostTrap"
#define BEACON_UUID         "E1F25DCB-1FDD-42D3-A9CF-97B024B9BD8A"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0xA5, 0x44, 0xF8, 0x8F, 0x3D}

#elif defined(MEDIUM)
#define DEVICE_NAME         "EctoGoggles"
#define BEACON_UUID         "8FE71AB9-7775-4DED-B4DD-E9AB6516D87B"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x8B, 0x6B, 0x71, 0xEE, 0x8A}

#elif defined(DIFFICULT)
#define DEVICE_NAME         "PKEMeter"
#define BEACON_UUID         "D80643E6-4C88-400D-9620-4F2C3D5E5BDE"
#define MANUFACTURER_ID     0x4c00
#define MAJOR               5
#define MINOR               88
#define SIGNAL_POWER        0xc5
#define MAC_ADDR            {0xF2, 0x0E, 0x84, 0xFB, 0x96, 0x7C}

#endif
