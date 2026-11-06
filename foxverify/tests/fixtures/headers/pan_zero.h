// EASY asks for a random PAN ID and channel, HARD for PAN ID zero on channel 11.
#if defined(COORDINATOR)
#if defined(EASY)
#define MAC_ADDR {0xF2, 0x5A, 0x3C, 0x91, 0x0E, 0x7B, 0x44, 0xD8}
#define EXT_PAN_ID MAC_ADDR
#define CHANNEL 0
#define PAN_ID 0
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define PACKET_INTERVAL 1
#define TXPOWER 20
#endif
#if defined(HARD)
#define MAC_ADDR {0xF2, 0xA7, 0x19, 0x62, 0xC3, 0x08, 0xBE, 0x35}
#define EXT_PAN_ID {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88}
#define CHANNEL 11
#define PAN_ID 0x0000
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
#define PACKET_INTERVAL 15
#define TXPOWER -15
#endif
#endif
