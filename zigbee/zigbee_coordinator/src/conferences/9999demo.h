// MAC addresses are rolled by make_conference: random, unicast and locally
// administered, so the first byte is even and ends in 2, 6, A or E.

// Note: https://docs.espressif.com/projects/esp-test-tools/en/latest/esp32c5/development_stage/rf_test_items/zigbee_non_signaling_test.html

// TXPOWER is in dBm, -15 to 20 on the ESP32-C5

// TXPOWER range: https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_hal_ieee802154/esp32c5/include/hal/ieee802154_ll.h

// IEEE802154_TXPOWER_VALUE_MIN -15
// IEEE802154_TXPOWER_VALUE_MAX 20

#if defined(COORDINATOR)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "Zigbee Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Easy Fox?'"
// 8 bytes (EUI-64), first byte even (I/G bit clear)
#define MAC_ADDR {0xF2, 0x5A, 0x3C, 0x91, 0x0E, 0x7B, 0x44, 0xD8}
// Extended PAN ID, 8 bytes in the same order as the MAC above. Zigbee
// defaults it to the coordinator MAC, which the value below keeps. Only
// beacons carry it, so Kismet shows it after something scans the channel.
#define EXT_PAN_ID MAC_ADDR
// 0 random every wake, or 11-26
#define CHANNEL 15
// PAN ID 0x0000-0xFFFE, make_conference rolls one per fox. Kismet names
// the device "PAN ID / short address"; a coordinator's short address is
// always 0x0000. A bare 0 rolls a new PAN ID every wake, which makes the
// fox hard to track. Write 0x0000 for PAN ID zero.
#define PAN_ID 0x1337
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 1
// Seconds between packets, 1-255 and less than TIME_TO_WAKE. Zigbee's default is 15
#define PACKET_INTERVAL 1
// dBm, -15 to 20
#define TXPOWER 20
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "Zigbee Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Hard Fox?'"
// 8 bytes (EUI-64), first byte even (I/G bit clear)
#define MAC_ADDR {0xF2, 0xA7, 0x19, 0x62, 0xC3, 0x08, 0xBE, 0x35}
// Extended PAN ID, 8 bytes in the same order as the MAC above. Zigbee
// defaults it to the coordinator MAC, which the value below keeps. Only
// beacons carry it, so Kismet shows it after something scans the channel.
#define EXT_PAN_ID MAC_ADDR
// 0 random every wake, or 11-26
#define CHANNEL 11
// PAN ID 0x0000-0xFFFE, make_conference rolls one per fox. Kismet names
// the device "PAN ID / short address"; a coordinator's short address is
// always 0x0000. A bare 0 rolls a new PAN ID every wake, which makes the
// fox hard to track. Write 0x0000 for PAN ID zero.
#define PAN_ID 0xDEAD
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds asleep, 0 reboots at once
#define TIME_TO_SLEEP 1
// Seconds between packets, 1-255 and less than TIME_TO_WAKE. Zigbee's default is 15
#define PACKET_INTERVAL 15
// dBm, -15 to 20
#define TXPOWER 20
#endif
#endif
