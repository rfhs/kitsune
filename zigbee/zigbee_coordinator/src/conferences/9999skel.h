// MAC addresses are rolled by make_conference: random, unicast and locally
// administered, so the first byte is even and ends in 2, 6, A or E.

// Note: https://docs.espressif.com/projects/esp-test-tools/en/latest/esp32c5/development_stage/rf_test_items/zigbee_non_signaling_test.html

// TXPOWER is in dBm, -15 to 20 on the ESP32-C5

// TXPOWER range: https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_hal_ieee802154/esp32c5/include/hal/ieee802154_ll.h#L11-L12

// IEEE802154_TXPOWER_VALUE_MIN -15
// IEEE802154_TXPOWER_VALUE_MAX 20

#if defined(COORDINATOR)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "Zigbee Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Easy Fox?'"
// 8 bytes (EUI-64), first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}
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
#define PAN_ID 0x0001
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP 0
// Seconds between packets, 1-255 and less than TIME_TO_WAKE. Zigbee's default is 15
#define PACKET_INTERVAL 1
// dBm, -15 to 20
#define TXPOWER 20
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "Zigbee Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Hard Fox?'"
// 8 bytes (EUI-64), first byte even (I/G bit clear)
#define MAC_ADDR {0x00, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e}
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
#define PAN_ID 0x0002
// Seconds awake, at least 1. Keep it to a few minutes so the startup
// checks and the LED run often
#define TIME_TO_WAKE 300
// Seconds off the air, 0 reboots at once. The fox shortens its sleep by its
// boot time so one cycle is exactly TIME_TO_WAKE + TIME_TO_SLEEP
#define TIME_TO_SLEEP 0
// Seconds between packets, 1-255 and less than TIME_TO_WAKE. Zigbee's default is 15
#define PACKET_INTERVAL 15
// dBm, -15 to 20
#define TXPOWER 20
#endif
#endif
