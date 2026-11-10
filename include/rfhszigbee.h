#include "Zigbee.h"
#include "esp_mac.h"
#include <rfhsconfcheck.h>

// The coordinator's one endpoint. The fox only transmits to be heard, so
// nothing ever talks to it.
#define ZIGBEE_ENDPOINT 1

// Exactly one difficulty, so exactly one block of the conference header
// defines the values below.
#ifndef COORDINATOR
#error "Build with -D COORDINATOR"
#endif
#if (defined(EASY) + defined(HARD)) != 1
#error "Build with exactly one of -D EASY or -D HARD"
#endif
// CHANNEL: 802.15.4 has channels 11-26 at 2.4 GHz. 0 picks one at random
// every wake.
#ifndef CHANNEL
#error "CHANNEL must be defined in the conference header, 0 for random or 11-26"
#elif CHANNEL != 0 && (CHANNEL < 11 || CHANNEL > 26)
#error "CHANNEL must be 0 (random) or 11-26"
#endif
// TXPOWER in dBm. The ESP32-C5 radio does IEEE802154_TXPOWER_VALUE_MIN to
// IEEE802154_TXPOWER_VALUE_MAX, -15 to 20.
#ifndef TXPOWER
#error "TXPOWER must be defined in the conference header, -15 to 20 dBm"
#elif TXPOWER < -15 || TXPOWER > 20
#error "TXPOWER must be -15 to 20 dBm"
#endif
// PACKET_INTERVAL: the stack stores the link status period as uint8_t
// seconds. It has to fit inside one wake or the fox never transmits.
#ifndef PACKET_INTERVAL
#error "PACKET_INTERVAL must be defined in the conference header, 1-255 seconds and less than TIME_TO_WAKE"
#elif PACKET_INTERVAL < 1 || PACKET_INTERVAL > 255
#error "PACKET_INTERVAL must be 1-255 seconds"
#elif defined(TIME_TO_WAKE) && PACKET_INTERVAL >= TIME_TO_WAKE
#error "PACKET_INTERVAL must be less than TIME_TO_WAKE or the fox sleeps before it transmits"
#endif
// 0xFFFF is the 802.15.4 broadcast PAN ID, so it can't be ours
#ifndef PAN_ID
#error "PAN_ID must be defined in the conference header, a bare 0 for random or 0x0000-0xFFFE"
#elif PAN_ID < 0 || PAN_ID > 0xFFFE
#error "PAN_ID must be a bare 0 (random) or 0x0000-0xFFFE"
#endif
// A bare 0 means "random PAN ID", 0x0000 means PAN ID zero. #if sees the
// same number either way, so compare the macro's text.
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
// MAC_ADDR is the IEEE 802.15.4 EUI-64, 8 bytes most significant first.
// Bit 0 of the first byte is the I/G bit and a device address has it
// clear. esp_iface_mac_addr_set checks nothing, so this is the only check.
#ifndef MAC_ADDR
#error "MAC_ADDR must be defined in the conference header, 8 bytes"
#endif
// EXT_PAN_ID is 8 bytes in the same order. All zeros means "not on a
// network" to the stack and all 0xFF is the wildcard, so neither can
// name a network.
#ifndef EXT_PAN_ID
#error "EXT_PAN_ID must be defined in the conference header, 8 bytes like MAC_ADDR or just MAC_ADDR"
#endif

ZigbeeGateway zbCoordinator = ZigbeeGateway(ZIGBEE_ENDPOINT);

constexpr uint8_t mac_addr[] = MAC_ADDR;
RFHS_CHECK_ADDRESS(mac_addr, 8);
// Most significant byte first like MAC_ADDR; rfhsstartradio() reverses it
// for the stack.
constexpr uint8_t ext_pan_id[] = EXT_PAN_ID;
static_assert(sizeof(ext_pan_id) == 8, "EXT_PAN_ID must be exactly 8 bytes");
static_assert(!rfhs_all_bytes(ext_pan_id, 8, 0x00), "EXT_PAN_ID must not be all zeros, the stack reads that as no network");
static_assert(!rfhs_all_bytes(ext_pan_id, 8, 0xFF), "EXT_PAN_ID must not be all 0xFF, that is the wildcard");
int set_channel;

// The awake LED colour: cyan for Zigbee.
#define RFHS_AWAKE_COLOR 0x00FFFF
constexpr uint32_t rfhs_awake_color = RFHS_AWAKE_COLOR;

bool rfhssetzigbeemac() {
  // This has to run before the stack starts: the stack reads the address
  // once, when it initializes.
  if (esp_iface_mac_addr_set(mac_addr, ESP_MAC_IEEE802154) == ESP_OK) {
    return true;
  } else {
    return false;
  }
}

// Sets the address, forms the network on the conference channel and applies
// the power, PAN ID, extended PAN ID and packet interval to it.
bool rfhsstartradio() {
  if (!rfhsmacset(rfhssetzigbeemac())) {
    return false;
  }
#if CHANNEL > 0
  set_channel = CHANNEL;
#else
  // 802.15.4 has only channels 11-26 at 2.4 GHz.
  set_channel = 11 + (esp_random() % 16);
#endif
  // The channel goes out before the radio starts, so a sniffer that reads
  // it over serial can be on the channel for the network formation. The
  // flush moves the line out of the USB FIFO before the start. The host may
  // not have the port open this early, so the Operating channel readback
  // after the start remains the record. The PAN ID has no such line: for a
  // random PAN_ID the stack picks it during formation.
  Serial.printf("Starting on channel %d\r\n", set_channel);
  Serial.flush();
  Zigbee.addEndpoint(&zbCoordinator);
  Zigbee.setPrimaryChannelMask(1 << set_channel);
  // The true erases the network saved before sleep, so the stack forms a
  // new one on our channel instead of rejoining the old one.
  if (!Zigbee.begin(ZIGBEE_COORDINATOR, true)) {
    Serial.println("Error starting Zigbee");
    return false;
  }
  esp_zb_lock_acquire(portMAX_DELAY);
  esp_zb_set_tx_power(TXPOWER);
  if (!pan_id_random) {
    // The stack formed the network on a random PAN ID. Nothing has joined
    // yet, so it can be swapped for ours.
    esp_zb_set_pan_id(PAN_ID);
  }
  // The stack formed the network with our MAC as the extended PAN ID.
  // EXT_PAN_ID replaces it, least significant byte first like the MAC.
  esp_zb_ext_pan_id_t ext_pan_id_le;
  for (int i = 0; i < sizeof(ext_pan_id); i++) {
    ext_pan_id_le[i] = ext_pan_id[sizeof(ext_pan_id) - 1 - i];
  }
  esp_zb_nwk_set_extended_pan_id(ext_pan_id_le);
  // The periodic packet hunters hear is the Link Status broadcast. The
  // Zigbee default is one every 15 seconds.
  esp_err_t err = esp_zb_nwk_set_link_status_period(PACKET_INTERVAL);
  esp_zb_lock_release();
  if (err != ESP_OK) {
    Serial.printf("Error setting packet interval: %s\r\n", esp_err_to_name(err));
    return false;
  }
  return true;
}

// Reads back what the stack is using, prints it and refuses to run when it
// is not what the conference header asked for.
bool rfhscheckradio() {
  // The stack stores the address least significant byte first, so it is
  // printed and compared from the last byte.
  esp_zb_ieee_addr_t long_addr;
  esp_zb_get_long_address(long_addr);
  if (!rfhscheckaddress(long_addr, mac_addr, sizeof(mac_addr), true)) {
    return false;
  }
  if (!rfhscheckint("Operating channel", "channel", esp_zb_get_current_channel(), set_channel, "")) {
    return false;
  }
  // A random PAN ID has nothing to be compared with, so it is compared with
  // itself and only printed.
  unsigned pan_id = esp_zb_get_pan_id();
  if (!rfhscheckhex16("Operating PAN ID", "PAN ID", pan_id, pan_id_random ? pan_id : PAN_ID, false)) {
    return false;
  }
  // The stack stores it least significant byte first, like the MAC.
  esp_zb_ext_pan_id_t read_ext_pan_id;
  esp_zb_nwk_get_extended_pan_id(read_ext_pan_id);
  if (!rfhscheckbytes("Extended PAN ID", "extended PAN ID", read_ext_pan_id, ext_pan_id, sizeof(ext_pan_id), true)) {
    return false;
  }
  // Zigbee gives the coordinator short address 0x0000 and the stack has
  // no public way to change it once the network exists. Kismet shows it
  // next to the PAN ID, so make sure it really is 0x0000.
  if (!rfhscheckhex16("Short address", "short address", esp_zb_get_short_address(), 0x0000, false)) {
    return false;
  }
  if (!rfhscheckint("Packet interval", "packet interval", esp_zb_nwk_get_link_status_period(), PACKET_INTERVAL, "s")) {
    return false;
  }
  // The radio stores the power per channel; rfhsstartradio() set every
  // channel to TXPOWER and this reads the operating channel's value back.
  int8_t tx_power;
  esp_zb_get_tx_power(&tx_power);
  return rfhscheckint("Tx power", "tx power", tx_power, TXPOWER, " dBm");
}

void rfhsstopradio() {
  Zigbee.stop();
}
