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
static_assert(sizeof(rfhs_bt_mac) == 6, "MAC_ADDR must be exactly 6 bytes");
static_assert((rfhs_bt_mac[0] & 0x01) == 0, "MAC_ADDR: bit 0 of the first byte (I/G) must be 0, use an even first byte");
static_assert(!rfhs_all_bytes(rfhs_bt_mac, 6, 0x00), "MAC_ADDR must not be all zeros");
static_assert(!(rfhs_bt_mac[3] == 0x9E && rfhs_bt_mac[4] == 0x8B && rfhs_bt_mac[5] <= 0x3F),
    "MAC_ADDR: the last three bytes 9E:8B:00 to 9E:8B:3F are Bluetooth inquiry access codes, pick another LAP");

bool rfhssetbtmac() {
  uint8_t mac_addr[6] = MAC_ADDR;
  // https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/misc_system_api.html#mac-address
#ifdef CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES
#pragma message "The value of CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES is: " TOSTRING(CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES)
  if (CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES == 4) {
    mac_addr[5] -= 2;
  } else if (CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES == 2) {
    mac_addr[5] -= 1;
  }
#endif
#ifdef CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES
#pragma message "The value of CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES is: " TOSTRING(CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES)
  if (CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES == 4) {
    mac_addr[5] -= 2;
  } else if (CONFIG_ESP32S3_UNIVERSAL_MAC_ADDRESSES == 2) {
    mac_addr[5] -= 1;
  }
#endif
#ifdef CONFIG_ESP32C5_UNIVERSAL_MAC_ADDRESSES
#pragma message "The value of CONFIG_ESP32C5_UNIVERSAL_MAC_ADDRESSES is: " TOSTRING(CONFIG_ESP32C5_UNIVERSAL_MAC_ADDRESSES)
  if (CONFIG_ESP32C5_UNIVERSAL_MAC_ADDRESSES == 4) {
    mac_addr[5] -= 2;
  } else if (CONFIG_ESP32C5_UNIVERSAL_MAC_ADDRESSES == 2) {
    mac_addr[5] -= 1;
  }
#endif
  if (esp_base_mac_addr_set(mac_addr) == ESP_OK) {
    return true;
  } else {
    return false;
  }
}

// Prints the address the Bluetooth controller is using and refuses to run
// when it differs from MAC_ADDR. addr is what esp_bt_dev_get_address()
// returned: the six bytes, or NULL when the stack is not enabled.
bool rfhscheckbtaddress(const uint8_t *addr) {
  if (addr == NULL) {
    Serial.println("Device address: unavailable, the Bluetooth stack is not enabled");
    return false;
  }
  Serial.printf("Device address: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
      addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
  for (size_t i = 0; i < sizeof(rfhs_bt_mac); i++) {
    if (addr[i] != rfhs_bt_mac[i]) {
      Serial.printf("Requested address: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
          rfhs_bt_mac[0], rfhs_bt_mac[1], rfhs_bt_mac[2],
          rfhs_bt_mac[3], rfhs_bt_mac[4], rfhs_bt_mac[5]);
      Serial.println("Device address != Requested address");
      return false;
    }
  }
  return true;
}
