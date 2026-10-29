#include "Zigbee.h"
#include "esp_mac.h"

// coordinator. we are just screaming and want to be heard
#define ZIGBEE_ENDPOINT 1

// the stack stores the link status period as uint8_t seconds
#if PACKET_INTERVAL < 1 || PACKET_INTERVAL > 255
#error "PACKET_INTERVAL must be defined as 1-255 seconds in the conference header"
#endif

ZigbeeGateway zbCoordinator = ZigbeeGateway(ZIGBEE_ENDPOINT);

const uint8_t mac_addr[8] = MAC_ADDR;
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
