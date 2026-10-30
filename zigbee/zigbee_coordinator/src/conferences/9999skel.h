// Bash to generate MAC address
// Note: 802.15.4 uses an 8 byte (EUI-64) address
// Note: least significant bit of first byte must be zero, here it's fixed to 0xF2
// printf '0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n' $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256] $[RANDOM%256]

// Note: https://docs.espressif.com/projects/esp-test-tools/en/latest/esp32c5/development_stage/rf_test_items/zigbee_non_signaling_test.html

// TXPOWER is in dBm, -15 to 20 on the ESP32-C5

// TXPOWER range: https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_hal_ieee802154/esp32c5/include/hal/ieee802154_ll.h#L11-L12

// IEEE802154_TXPOWER_VALUE_MIN -15
// IEEE802154_TXPOWER_VALUE_MAX 20

#if defined(COORDINATOR)
#if defined(EASY)
// RFHS_CHALLENGE_NAME "Zigbee Easy Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Easy Fox?'"
// set mac address
#define MAC_ADDR {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}
// Extended PAN ID, 8 bytes in the same order as the MAC above. Zigbee
// defaults it to the coordinator MAC, which the value below keeps. Only
// beacons carry it, so Kismet shows it after something scans the channel.
#define EXT_PAN_ID MAC_ADDR
// Channel 11-26.
// 16 channels in total permitted. 0 means random
#define CHANNEL 15
// PAN ID 0x0000-0xFFFE, make_conference rolls one per fox. Kismet names
// the device "PAN ID / short address"; a coordinator's short address is
// always 0x0000. A bare 0 rolls a new PAN ID every wake, which makes the
// fox hard to track. Write 0x0000 for PAN ID zero.
#define PAN_ID 0x0001
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
// seconds between packets, 1-255. Zigbee default is 15.
// keep it well under TIME_TO_WAKE or the fox may sleep before it talks
#define PACKET_INTERVAL 1
#define TXPOWER 20
#endif

#if defined(HARD)
// RFHS_CHALLENGE_NAME "Zigbee Hard Fox"
// FOX_KEYWORDS "Hunter should ask 'Are you the Zigbee Hard Fox?'"
// set mac address
#define MAC_ADDR {0x00, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e}
// Extended PAN ID, 8 bytes in the same order as the MAC above. Zigbee
// defaults it to the coordinator MAC, which the value below keeps. Only
// beacons carry it, so Kismet shows it after something scans the channel.
#define EXT_PAN_ID MAC_ADDR
// Channel 11-26.
// 16 channels in total permitted. 0 means random
#define CHANNEL 11
// PAN ID 0x0000-0xFFFE, make_conference rolls one per fox. Kismet names
// the device "PAN ID / short address"; a coordinator's short address is
// always 0x0000. A bare 0 rolls a new PAN ID every wake, which makes the
// fox hard to track. Write 0x0000 for PAN ID zero.
#define PAN_ID 0x0002
// checks run during startup so we want to stay
// running no longer than a few minutes to force
// checks to run and led to update
#define TIME_TO_WAKE 300
#define TIME_TO_SLEEP 1
// seconds between packets, 1-255. Zigbee default is 15.
// keep it well under TIME_TO_WAKE or the fox may sleep before it talks
#define PACKET_INTERVAL 15
#define TXPOWER 20
#endif
#endif
