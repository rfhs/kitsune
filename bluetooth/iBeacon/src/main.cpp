#include <Arduino.h>

#include "current_conf.h"

#include <rfhsledmacros.h>
#include <rfhssleeptimers.h>
#include <rfhsibeacon.h>

void setup() {
  Serial.begin(115200);
  Serial.flush();
  Serial.println("Initializing...");
  rfhsledinit();
  rfhsboottimer();
  Serial.flush();

  rfhsstartibeacon();
  ledcolor(0x0000FF); // BLUE
  Serial.println("iBeacon advertising!");
  #ifdef DEEP_SLEEP
  delay(ADVERTISING_DURATION * 1000);

  ledcolor(0x880000);  // HALF RED
  pAdvertising->stop();
  Serial.println("entering deep sleep");
  ledcolor(0xff0000);  // RED
  delay(50);
  esp_deep_sleep(1000000LL * GPIO_DEEP_SLEEP_DURATION);
  // This line should never run so it's a canary for sleep failed
  rfhsledfatal();
  #endif
}

void loop() {
  #ifdef DEEP_SLEEP
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  rfhsledfatal();
  #endif
}
