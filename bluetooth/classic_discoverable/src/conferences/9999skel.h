#if defined(EASY)
// RFHS_CHALLENGE_NAME "Bluetooth Classic Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Bluetooth Classic Easy Fox?'"
// Name hunters see, 1-32 characters
#define NAME "Molly BTC Easy Fox"
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR {0x00, 0x01, 0x02, 0x03, 0x04, 0x05}
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
#define NAME "Case BTC Hard Fox"
// 6 bytes, first byte even (I/G bit clear), last three bytes not 9E:8B:00-9E:8B:3F
#define MAC_ADDR {0x00, 0x06, 0x07, 0x08, 0x09, 0x0a}
// Seconds awake, at least 15 so a Bluetooth inquiry can reach the fox
#define TIME_TO_WAKE 30
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP 30
#endif
