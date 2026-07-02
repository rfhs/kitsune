#include "esp_mac.h"

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)

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
