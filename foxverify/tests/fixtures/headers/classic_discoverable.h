// Frozen copy of bluetooth/classic_discoverable/src/conferences/9999demo.h for the tests. The
// transcripts under ../transcripts and the literal values in the tests match
// this copy, not the live demo header, which is rolled anew each year.

#if defined(EASY)
// RFHS_CHALLENGE_NAME "Bluetooth Classic Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Bluetooth Classic Easy Fox?'"
// Name hunters see, 1-32 characters
#define NAME "Demo Molly BTC Easy Fox"
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR {0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x26}
// Seconds awake, at least 15 so a Bluetooth inquiry can reach the fox
#define TIME_TO_WAKE 300
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP 0
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "Bluetooth Classic Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Bluetooth Classic Hard Fox?'"
// Name hunters see, 1-32 characters
#define NAME "Demo Case BTC Hard Fox"
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR {0xF2, 0xF6, 0x6D, 0xBC, 0x2A, 0x80}
// Seconds awake, at least 15 so a Bluetooth inquiry can reach the fox
#define TIME_TO_WAKE 30
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP 30
#endif
