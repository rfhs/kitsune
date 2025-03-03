#include <WiFi.h>
#include <esp_wifi.h>

void disableWiFi() {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
}

uint8_t mac_addr[6] = MAC_ADDR;

