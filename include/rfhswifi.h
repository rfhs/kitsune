#include <WiFi.h>
#include <esp_wifi.h>

void disableWiFi() {
 // fixes a noisy log error when monitoring
#if defined(AP)
  WiFi.softAPdisconnect(true);
#elif defined(CLIENT)
  WiFi.disconnect(true);
#endif
  WiFi.mode(WIFI_OFF);
}
