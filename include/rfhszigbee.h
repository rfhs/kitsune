#include "Zigbee.h"
#include "esp_mac.h"

// coordinator. we are just screaming and want to be heard
#define ZIGBEE_ENDPOINT 1

// the stack stores the link status period as uint8_t seconds
#if PACKET_INTERVAL < 1 || PACKET_INTERVAL > 255
#error "PACKET_INTERVAL must be defined as 1-255 seconds in the conference header"
#endif
// 0xFFFF is the 802.15.4 broadcast PAN ID, so it can't be ours
#ifndef PAN_ID
#error "PAN_ID must be defined in the conference header, a bare 0 for random or 0x0000-0xFFFE"
#elif PAN_ID < 0 || PAN_ID > 0xFFFE
#error "PAN_ID must be a bare 0 (random) or 0x0000-0xFFFE"
#endif
// A bare 0 means "random PAN ID", 0x0000 means PAN ID zero. #if sees the
// same number either way, so compare the macro's text.
#define RFHS_STR_(x) #x
#define RFHS_STR(x) RFHS_STR_(x)
constexpr bool rfhs_str_eq(const char *a, const char *b) {
  return *a == *b && (*a == '\0' || rfhs_str_eq(a + 1, b + 1));
}
constexpr bool pan_id_random = rfhs_str_eq(RFHS_STR(PAN_ID), "0");

// FUTURE USE: short address rules, for a router or end device challenge.
// A coordinator is always 0x0000 and the stack won't change it once the
// network exists, so there is no SHORT_ADDR here. (PAN IDs are different:
// only 0xFFFF is reserved.)
//
// A device may use 0x0000-0xFFF7. 802.15.4 reserves:
//   0xFFFE  associated but has no short address, use the IEEE address
//   0xFFFF  broadcast to every device
// Zigbee reserves the whole 0xFFF8-0xFFFF block as NWK broadcasts, named
// in zboss_api_nwk.h:
//   0xFFFF  ZB_NWK_BROADCAST_ALL_DEVICES
//   0xFFFE  reserved
//   0xFFFD  ZB_NWK_BROADCAST_RX_ON_WHEN_IDLE, devices that keep the radio on
//   0xFFFC  ZB_NWK_BROADCAST_ROUTER_COORDINATOR
//   0xFFFB  ZB_NWK_BROADCAST_LOW_POWER_ROUTER
//   0xFFF8-0xFFFA  reserved, ZB_NWK_BROADCAST_RESERVED is the bottom of the block
// The stack sends anything >= 0xFFF8 as a broadcast, no ack, no retry.
// esp_zb_nwk_set_short_address() in test/esp_zigbee_test_utils.h only
// works before joining and only sets the NWK layer. Expect to pick the
// address before Zigbee.begin().
#ifndef EXT_PAN_ID
#error "EXT_PAN_ID must be defined in the conference header, 8 bytes like MAC_ADDR or just MAC_ADDR"
#endif

ZigbeeGateway zbCoordinator = ZigbeeGateway(ZIGBEE_ENDPOINT);

const uint8_t mac_addr[8] = MAC_ADDR;
// Most significant byte first like MAC_ADDR; rfhsstartzigbee reverses it
// for the stack.
const uint8_t ext_pan_id[] = EXT_PAN_ID;
static_assert(sizeof(ext_pan_id) == 8, "EXT_PAN_ID must be exactly 8 bytes");
int set_channel;

bool rfhssetzigbeemac() {
  // must run before the stack starts, it reads the address once at init
  if (esp_iface_mac_addr_set(mac_addr, ESP_MAC_IEEE802154) == ESP_OK) {
    return true;
  } else {
    return false;
  }
}

bool rfhsstartzigbee() {
#if CHANNEL > 0
  set_channel = CHANNEL;
#else
  // 802.15.4 only has channels 11-26 in 2.4GHz
  set_channel = 11 + (esp_random() % 16);
#endif
  Zigbee.addEndpoint(&zbCoordinator);
  Zigbee.setPrimaryChannelMask(1 << set_channel);
  // forget the network saved before sleep and start a new one on our channel
  if (!Zigbee.begin(ZIGBEE_COORDINATOR, true)) {
    Serial.println("Error starting Zigbee");
    return false;
  }
  esp_zb_lock_acquire(portMAX_DELAY);
  esp_zb_set_tx_power(TXPOWER);
  if (!pan_id_random) {
    // the stack formed the network on a random pan id. nothing has
    // joined, so swap in ours.
    esp_zb_set_pan_id(PAN_ID);
  }
  // the stack formed the network with our MAC as the extended pan id.
  // set EXT_PAN_ID, least significant byte first like the MAC.
  esp_zb_ext_pan_id_t ext_pan_id_le;
  for (int i = 0; i < sizeof(ext_pan_id); i++) {
    ext_pan_id_le[i] = ext_pan_id[sizeof(ext_pan_id) - 1 - i];
  }
  esp_zb_nwk_set_extended_pan_id(ext_pan_id_le);
  // the periodic packet hunters hear is the link status broadcast.
  // the zigbee default is one every 15 seconds.
  esp_err_t err = esp_zb_nwk_set_link_status_period(PACKET_INTERVAL);
  esp_zb_lock_release();
  if (err != ESP_OK) {
    Serial.printf("Error setting packet interval: %s\r\n", esp_err_to_name(err));
    return false;
  }
  return true;
}

// quick sanity check.
// read back what the stack is actually using.
// refuse to run if it isn't what we asked for.
bool rfhscheckzigbee() {
  esp_zb_ieee_addr_t long_addr;
  esp_zb_get_long_address(long_addr);
  // the stack stores the mac addr backwards.
  // so it prints and compares starting from the last byte
  Serial.printf("Started Coordinator with MAC Address: %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X\r\n",
      long_addr[7], long_addr[6], long_addr[5], long_addr[4],
      long_addr[3], long_addr[2], long_addr[1], long_addr[0]);
  for (int i = 0; i < sizeof(mac_addr); i++) {
    if (long_addr[sizeof(mac_addr) - 1 - i] != mac_addr[i]) {
      Serial.println("Read MAC Address != Requested Mac Address");
      return false;
    }
  }
  Serial.printf("Operating channel: %d\r\n", esp_zb_get_current_channel());
  if (esp_zb_get_current_channel() != set_channel) {
    Serial.printf("Requested channel: %d\r\n", set_channel);
    Serial.println("Operating channel != Requested Channel");
    return false;
  }
  Serial.printf("Operating PAN ID: 0x%04X\r\n", esp_zb_get_pan_id());
  if (!pan_id_random && esp_zb_get_pan_id() != PAN_ID) {
    Serial.printf("Requested PAN ID: 0x%04X\r\n", PAN_ID);
    Serial.println("Operating PAN ID != Requested PAN ID");
    return false;
  }
  // stored least significant byte first, same as the MAC
  esp_zb_ext_pan_id_t read_ext_pan_id;
  esp_zb_nwk_get_extended_pan_id(read_ext_pan_id);
  Serial.printf("Extended PAN ID: %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X\r\n",
      read_ext_pan_id[7], read_ext_pan_id[6], read_ext_pan_id[5], read_ext_pan_id[4],
      read_ext_pan_id[3], read_ext_pan_id[2], read_ext_pan_id[1], read_ext_pan_id[0]);
  for (int i = 0; i < sizeof(ext_pan_id); i++) {
    if (read_ext_pan_id[sizeof(ext_pan_id) - 1 - i] != ext_pan_id[i]) {
      Serial.println("Read Extended PAN ID != Requested Extended PAN ID");
      return false;
    }
  }
  // Zigbee gives the coordinator short address 0x0000 and the stack has
  // no public way to change it once the network exists. Kismet shows it
  // next to the PAN ID, so make sure it really is 0x0000.
  Serial.printf("Short address: 0x%04X\r\n", esp_zb_get_short_address());
  if (esp_zb_get_short_address() != 0x0000) {
    Serial.println("Short address != 0x0000");
    return false;
  }
  Serial.printf("Packet interval: %ds\r\n", esp_zb_nwk_get_link_status_period());
  if (esp_zb_nwk_get_link_status_period() != PACKET_INTERVAL) {
    Serial.printf("Requested packet interval: %ds\r\n", PACKET_INTERVAL);
    Serial.println("Packet interval != Requested packet interval");
    return false;
  }
  return true;
}

void disableZigbee() {
  Zigbee.stop();
}
