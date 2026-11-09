#include <Arduino.h>
#include "esp_mac.h"
#include "esp_bt_device.h"
#include <rfhsconfcheck.h>

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)

// MAC_ADDR is the Bluetooth device address, 6 bytes most significant first.
// Bit 0 of the first byte is the I/G bit; a device address has it clear
// and esp_base_mac_addr_set refuses anything else. The last three bytes
// are the Bluetooth LAP. The Core specification reserves LAPs 0x9E8B00 to
// 0x9E8B3F for inquiry access codes and forbids them in any device
// address. The address goes on air as a public address, so the BLE random
// address type bits in the first byte do not apply.
#ifndef MAC_ADDR
#error "MAC_ADDR must be defined in the conference header, 6 bytes"
#endif
constexpr uint8_t rfhs_bt_mac[] = MAC_ADDR;
RFHS_CHECK_ADDRESS(rfhs_bt_mac, 6);
static_assert(!(rfhs_bt_mac[3] == 0x9E && rfhs_bt_mac[4] == 0x8B && rfhs_bt_mac[5] <= 0x3F),
    "MAC_ADDR: the last three bytes 9E:8B:00 to 9E:8B:3F are Bluetooth inquiry access codes, pick another LAP");

// The controller derives the Bluetooth address from the base MAC: with four
// universal addresses it is the base plus 2, with two it is the base plus 1
// (esp_read_mac in the IDF). The base is set that much lower so the address
// on air is MAC_ADDR. Each core names the count after its chip, so a chip
// without a branch here refuses to build rather than go on air with the
// wrong address.
// https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/misc_system_api.html#mac-address
bool rfhssetbtmac() {
  uint8_t mac_addr[6] = MAC_ADDR;
#ifdef CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES
#pragma message "The value of CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES is: " TOSTRING(CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES)
  if (CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES == 4) {
    mac_addr[5] -= 2;
  } else if (CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES == 2) {
    mac_addr[5] -= 1;
  }
#elif defined(CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES)
#pragma message "The value of CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES is: " TOSTRING(CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES)
  if (CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES == 4) {
    mac_addr[5] -= 2;
  } else if (CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES == 2) {
    mac_addr[5] -= 1;
  }
#else
#error "rfhsbt.h: add this chip's universal MAC address count"
#endif
  if (esp_base_mac_addr_set(mac_addr) == ESP_OK) {
    return true;
  } else {
    return false;
  }
}

// Prints the address the Bluetooth controller is using and refuses to run
// when it differs from MAC_ADDR. addr is what esp_bt_dev_get_address()
// returned: the six bytes most significant first, or NULL when the stack is
// not enabled.
bool rfhscheckbtaddress(const uint8_t *addr) {
  if (addr == NULL) {
    Serial.println("Device address: unavailable, the Bluetooth stack is not enabled");
    return false;
  }
  return rfhscheckaddress(addr, rfhs_bt_mac, sizeof(rfhs_bt_mac), false);
}
