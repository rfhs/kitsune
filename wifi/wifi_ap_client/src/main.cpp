#include <Arduino.h>

#include "current_conf.h"
#include <rfhssleeptimers.h>
#include <rfhsledmacros.h>
#include <rfhswifi.h>

void setup() {
  // Bring up serial early so we can debug
  Serial.begin(115200);
  Serial.flush();

  // Initialize Wi-Fi with default configuration to set MAC address
  wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
  WiFi.mode(WIFI_MODE_NULL);
  esp_wifi_init(&cfg);
  esp_wifi_set_storage(WIFI_STORAGE_RAM);
  delay(100); // adjust the esp_deep_sleep if you change this
  esp_wifi_start();

  #if defined(AP)
  // Create Wi-Fi network with SSID and password
  Serial.println("Setting AP (Access Point)…");
  // Interface to set MAC address
  wifi_interface_t interface = WIFI_IF_AP;
  #elif defined(CLIENT)
  // Connect to Wi-Fi network with SSID and password
  Serial.println("Setting WiFi Fox Client…");
  // Interface to set MAC address
  wifi_interface_t interface = WIFI_IF_STA;
  #endif

  if (esp_wifi_set_mac(interface, mac_addr) == ESP_OK) {
    Serial.println("MAC address set successfully");
  } else {
    Serial.println("Error setting MAC address");
  }
  // Before this desired mac address is not set
  // Speed counts

  rfhsledinit();

  Serial.flush();
  Serial.println();
  Serial.println("Initializing...");
  rfhsboottimer();

  #if defined(AP)
  #if CHANNEL > 0
  int set_channel = CHANNEL;
  #else
  int set_channel = random(10);
  set_channel++;
  #endif
  Serial.printf("Setting channel to: %d\r\n", set_channel);
  Serial.flush();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(FSSID, PSK, set_channel, SSID_HIDDEN, MAX_CLIENTS);
  Serial.printf("Set power status: %s\r\n", String(WiFi.setTxPower(TXPOWER)));
  Serial.println("Started AP with MAC Address: " + String(WiFi.softAPmacAddress()));
  ledcolor(0x00ff00); // GREEN
  #elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  WiFi.begin(FSSID, PSK);
  ledcolor(0xfff700);  // YELLOW
  #endif

  // Before this desired config is not set
  // Speed counts
  Serial.println("Awake and screaming");
  
  delay(TIME_TO_WAKE * mS_TO_S);
  Serial.println("Going to sleep");
  ledcolor(0x880000);  // HALF RED
  disableWiFi();
  ledcolor(0xff0000);  // RED
  delay(75);  // adjust the esp_deep_sleep if you change this
  // subtract sleep time on line 39 and 105
  int sleepy_tyme = uS_TO_S * TIME_TO_SLEEP - 75 - 100;
  if (sleepy_tyme < 0 ) {
    sleepy_tyme = 0;
  }
  esp_deep_sleep(sleepy_tyme);
  // This line should never run so it's a canary for sleep failed
  rfhsledfatal();
}

void loop(){
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  rfhsledfatal();
}
