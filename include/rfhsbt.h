uint8_t mac_addr[6] = MAC_ADDR;

void rfhssetbtmac() {
  // https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/misc_system_api.html#mac-address
  mac_addr[5] -= 2;
  esp_base_mac_addr_set(mac_addr);
}
