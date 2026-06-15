#include <WiFi.h>
#include <esp_wifi.h>

void disableWiFi() {
 // fixes a noisy log error when monitoring
#if defined(AP)
  WiFi.softAPdisconnect(true);
#else
  WiFi.disconnect(true);
#endif
  WiFi.mode(WIFI_OFF);
}

uint8_t mac_addr[6] = MAC_ADDR;

