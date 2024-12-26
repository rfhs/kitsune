//LED support
#include <M5Atom.h>
// needed if we don't use M5Atom.h
//#include <Arduino.h>

#include "esp_sleep.h"
#include "sys/time.h"
#include "current_conf.h"
#include <WiFi.h>
#include <esp_wifi.h>

// microseconds are used by esp_sleep_enable_timer_wakeup
#define uS_TO_S 1000000
// milliseconds are used by delay
#define mS_TO_S 1000

RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
struct timeval now;

uint8_t mac_addr[6] = MAC_ADDR;

void disableWiFi(){
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
}

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

  M5.begin(false, false,true);
  //Needed if not using M5.begin()
  //Serial.begin(115200);
  Serial.flush();
  M5.dis.drawpix(0, 0x9400D3);  // DARKVIOLET
  Serial.println();
  Serial.println("Initializing...");
  gettimeofday(&now, NULL);
  Serial.printf("Start ESP32 %d\r\n", bootcount++);
  Serial.printf("deep sleep (%lds since last reset, %lds since last boot)\r\n", now.tv_sec, now.tv_sec - last);
  last = now.tv_sec;

  #if defined(AP)
  #if CHANNEL > 0
  int set_channel = CHANNEL;
  #else
  int set_channel = random(10);
  set_channel++;
  #endif
  Serial.printf("Setting channel to: %d\n", set_channel);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(FSSID, PSK, set_channel, SSID_HIDDEN, MAX_CLIENTS);
  Serial.print("Set power status: ");
  Serial.println(WiFi.setTxPower(TXPOWER));
  Serial.print("\nStarted AP with MAC Address: ");
  Serial.println(WiFi.softAPmacAddress());
  M5.dis.drawpix(0, 0x00ff00); // GREEN
  #elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  WiFi.begin(FSSID, PSK);
  M5.dis.drawpix(0, 0xfff000);  // YELLOW
  #endif

  // Before this desired config is not set
  // Speed counts
  Serial.println("Awake and screaming");
  
  delay(TIME_TO_WAKE * mS_TO_S);
  Serial.println("Going to sleep");
  M5.dis.drawpix(0, 0x880000);  // HALF RED
  disableWiFi();
  M5.dis.drawpix(0, 0xff0000);  // RED
  delay(75);  // adjust the esp_deep_sleep if you change this
  // subtract sleep time on line 39 and 105
  int sleepy_tyme = uS_TO_S * TIME_TO_SLEEP - 75 - 100;
  if (sleepy_tyme < 0 ) {
    sleepy_tyme = 0;
  }
  esp_deep_sleep(sleepy_tyme);
  // This line should never run so it's a canary for sleep failed
  M5.dis.drawpix(0, 0xFFF700);  // Yellow
}

void loop(){
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  delay(200);
  M5.dis.drawpix(0, 0xff0000);  // RED
  delay(200);
  M5.dis.drawpix(0, 0xFFF700);  // Yellow
}
