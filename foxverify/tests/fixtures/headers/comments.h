// A header whose comments mention defines the parser must not see.
// #define TRAP_LINE 1
//#define TRAP_NO_SPACE 2
/* #define TRAP_BLOCK 3 */
/*
 * #define TRAP_MULTILINE 4
 * #if defined(HARD)
 */
//WIFI_POWER_19_5dBm 78
#if defined(EASY)
// RFHS_CHALLENGE_NAME "Comment Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Comment Fox?'"
#define NAME "Slashes // inside a string stay" // trailing comment
#define MAC_ADDR {0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x26} /* trailing block */
#define TIME_TO_WAKE /* a comment in the middle */ 300
#define TIME_TO_SLEEP 0
#endif
#if defined(HARD)
#define NAME "Hard Comment Fox"
#define MAC_ADDR {0xF2, 0xF6, 0x6D, 0xBC, 0x2A, 0x80}
#define TIME_TO_WAKE 30
#define TIME_TO_SLEEP 30
#endif
