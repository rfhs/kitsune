#include <Arduino.h>

#include "current_conf.h"

#include "BluetoothSerial.h"

#include <rfhsledmacros.h>
#include <rfhssleeptimers.h>

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
#endif

BluetoothSerial SerialBT;

uint8_t mac_addr[6] = MAC_ADDR;

void setup() {
  Serial.begin(115200);
  rfhsledinit();
  Serial.flush();
  Serial.println("Initializing...");
  rfhsboottimer();
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
