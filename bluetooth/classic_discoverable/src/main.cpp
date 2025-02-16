#include <Arduino.h>

#include "esp_sleep.h"
#include "sys/time.h"
#include "current_conf.h"

#include "BluetoothSerial.h"

#include <rfhsledmacros.h>

// microseconds are used by esp_sleep_enable_timer_wakeup
#define uS_TO_S 1000000
// milliseconds are used by delay
#define mS_TO_S 1000

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
#endif

BluetoothSerial SerialBT;

uint8_t mac_addr[6] = MAC_ADDR;

RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
struct timeval now;

void setup() {
  Serial.begin(115200);
  rfhsledinit();
  Serial.flush();
  Serial.println("Initializing...");
  gettimeofday(&now, NULL);
  Serial.printf("Start ESP32 %d\r\n", bootcount++);
  Serial.printf("deep sleep (%lds since last reset, %lds since last boot)\r\n", now.tv_sec, now.tv_sec - last);
  last = now.tv_sec;
  Serial.flush();

  // https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/misc_system_api.html#mac-address
  mac_addr[5] -= 2;
  esp_base_mac_addr_set(mac_addr);
  // String localName=String(), bool isMaster=false
  SerialBT.begin(NAME, false); //Bluetooth device name

  ledcolor(0x0000FF); // BLUE
  delay(TIME_TO_WAKE * mS_TO_S);
  Serial.println("Going to sleep");
  ledcolor(0xff0000);  // RED
  delay(75);  // adjust the esp_deep_sleep if you change this
  // subtract sleep time on line 44
  int sleepy_tyme = uS_TO_S * TIME_TO_SLEEP - 75;
  if (sleepy_tyme < 100 ) {
    sleepy_tyme = 100;
  }
  esp_deep_sleep(sleepy_tyme);
  // This line should never run so it's a canary for sleep failed
  rfhsledfatal();
}

void loop() {
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  rfhsledfatal();
}
