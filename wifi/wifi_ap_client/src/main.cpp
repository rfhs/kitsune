#include <Arduino.h>

#include "current_conf.h"
#include <rfhssleeptimers.h>
#include <rfhsledmacros.h>
#include <rfhswifi.h>
#include <esp_mac.h>
#include <esp_system.h>
#include <esp_log.h>

void setup() {
  // Bring up serial early so we can debug
  Serial.begin(115200);
  Serial.flush();

  // Initialize Wi-Fi with default configuration to set MAC address
  wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
  #if defined(AP)
  WiFi.mode(WIFI_AP);
  #elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  #endif
  esp_wifi_init(&cfg);
  // esp_wifi_start(); // esp_wifi_set_mac() only requires Wi-Fi to be *initialized*

  #if defined(AP)
  // Create Wi-Fi network with SSID and password
  Serial.println("Setting up AP (Access Point)…");
  // Interface to set MAC address
  wifi_interface_t interface = WIFI_IF_AP;
  #elif defined(CLIENT)
  // Connect to Wi-Fi network with SSID and password
  Serial.println("Setting up WiFi Client…");
  // Interface to set MAC address
  wifi_interface_t interface = WIFI_IF_STA;
  #endif

  // Before this desired mac address is not set
  // Speed counts
  uint8_t mac_addr[6] = MAC_ADDR;
  if (esp_wifi_set_mac(interface, mac_addr) == ESP_OK) {
    Serial.println("MAC address set successfully");
  } else {
    Serial.println("Error setting MAC address");
  }

  //  If this runs before setting mac address then
  //  setting mac address fails on esp32c5
  esp_wifi_set_storage(WIFI_STORAGE_RAM);

  rfhsledinit();

  Serial.flush();
  Serial.println();
  Serial.println("Initializing...");
  rfhsboottimer();

  // Set the regulatory domain BEFORE starting the radio
  // Use the 2-letter ISO code (e.g., "US", "DE", "JP", "CN")
  // The second parameter 'true' tells the chip to enforce these rules tightly
  esp_err_t err = esp_wifi_set_country_code("US", true);

  if (err == ESP_OK) {
    ESP_LOGI("WIFI", "Regulatory domain successfully set to US.");
  } else {
    ESP_LOGE("WIFI", "Failed to set country code: %s", esp_err_to_name(err));
  }

  char mac_str[18];
  snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
      mac_addr[0], mac_addr[1], mac_addr[2],
      mac_addr[3], mac_addr[4], mac_addr[5]);
  #if defined(AP)
  #if CHANNEL > 0
  int set_channel = CHANNEL;
  #else
  #if defined(FIVEEASY) || defined(FIVEHARD)

  /*
  // Directly stolen channel list from https://github.com/CoD-Segfault/wifi-shuriken/blob/main/include/channel_scheduler.h on 2026-07-03
  // He worked it out by brute force
  //static constexpr uint8_t CHANNEL_LIST_5G[] = {
  //  36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124,
  //  128, 132, 136, 140, 144, 149, 153, 157, 161, 165
  //};
  */
  static constexpr uint8_t CHANNEL_LIST_5G[] = {
    36, 40, 44, 48, 149, 153, 157, 161, 165
  };
  constexpr size_t total_elements = sizeof(CHANNEL_LIST_5G) / sizeof(CHANNEL_LIST_5G[0]);
  size_t random_index = esp_random() % total_elements;
  uint8_t set_channel = CHANNEL_LIST_5G[random_index];
  #else
  // Intentionally limited to worldwide allowed channels
  uint8_t set_channel = esp_random() % 11;
  set_channel++;
  #endif
  #endif
  WiFi.mode(WIFI_AP);
  WiFi.softAP(FSSID, PSK, set_channel, SSID_HIDDEN, MAX_CLIENTS);
  delay(100); // Let AP start before we run our checks
  Serial.printf("Set power status: %s\r\n", String(WiFi.setTxPower(TXPOWER)));
  Serial.println("Started AP with MAC Address: " + WiFi.softAPmacAddress());
  if (WiFi.softAPmacAddress() != mac_str){
    Serial.println("Requested MAC address      : " + String(mac_str));
    Serial.println("Read MAC Address != Requested Mac Address");
    Serial.flush();
    disableWiFi();
    rfhsledfatal();
  }
  uint8_t currentChannel = WiFi.channel();
  Serial.printf("Operating channel: %d\r\n", currentChannel);
  if (currentChannel != set_channel){
    Serial.printf("Requested channel: %d\r\n", set_channel);
    Serial.println("Operating channel != Requested Channel");
    Serial.flush();
    disableWiFi();
    rfhsledfatal();
  }
  String currentSSID = WiFi.softAPSSID();
  Serial.println("Operating SSID: " + currentSSID);
  if (String(FSSID) != currentSSID){
    Serial.println("Requested SSID: " FSSID);
    Serial.println("Operating SSID != Requested SSID");
    Serial.flush();
    disableWiFi();
    rfhsledfatal();
  }
  Serial.flush();
  ledcolor(0x00ff00); // GREEN
  #elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  WiFi.begin(FSSID, PSK);
  delay(100); // Let Client start before we run our checks
  Serial.println("Started Client with MAC Address: " + WiFi.macAddress());
  if (WiFi.macAddress() != mac_str){
    Serial.println("Read MAC Address != Requested Mac Address");
    Serial.flush();
    disableWiFi();
    rfhsledfatal();
  }
  Serial.flush();
  ledcolor(0xff8c00);  // ORANGE
  #endif

  // Before this desired config is not set
  // Speed counts
  Serial.println("Awake and screaming");

  delay(TIME_TO_WAKE * mS_TO_S);
  Serial.println("Going to sleep");
  ledcolor(0x880000);  // HALF RED
  disableWiFi();
  ledcolor(0xff0000);  // RED
  delay(75); // Give the led time to set before sleeping
  // subtract sleep time on line 101, 134, 155
  int sleepy_tyme = uS_TO_S * TIME_TO_SLEEP - 75 - 100 ;
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
