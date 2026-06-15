#include <Arduino.h>

#include "current_conf.h"
#include <rfhssleeptimers.h>
#include <rfhsledmacros.h>
#include <rfhswifi.h>
#include <esp_mac.h>

void setup() {
  // Bring up serial early so we can debug
  Serial.begin(115200);
  Serial.flush();

  WiFi.persistent(false); // Stores it still in RAM

  #if defined(AP)
  // Create Wi-Fi network with SSID and password
  Serial.println("Setting AP (Access Point)…");
  mac_addr[5] -=1;
  #elif defined(CLIENT)
  // Connect to Wi-Fi network with SSID and password
  Serial.println("Setting WiFi Fox Client…");
  #endif
  if (esp_base_mac_addr_set(mac_addr) == ESP_OK) {
    Serial.println("MAC address set successfully");
  } else {
    Serial.println("Error setting MAC address");
  }
  delay(100); // adjust the esp_deep_sleep if you change this

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
  delay(75); // adjust the esp_deep_sleep if you change this
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
