#include <Arduino.h>

#include "current_conf.h"

#include <rfhsledmacros.h>
#include <rfhssleeptimers.h>
#include <rfhsbanner.h>
#include <rfhsibeacon.h>

void setup() {
  Serial.begin(115200);
  Serial.flush();
  Serial.println("Initializing...");
  rfhsledinit();
  rfhsboottimer();
  Serial.flush();

  rfhsstartibeacon();
  // The radio is up, so the host has had time to open the port; see rfhsbanner.h.
  RFHS_BANNER("iBeacon");
  rfhsprintsleeptimers();
  if (!rfhscheckibeacon()) {
    Serial.flush();
    pAdvertising->stop();
    rfhsledfatal();
  }
  ledcolor(0x0000FF); // BLUE
  Serial.println("iBeacon advertising!");
  delay(TIME_TO_WAKE * mS_TO_S);

  ledcolor(0x880000);  // HALF RED
  pAdvertising->stop();
  Serial.println("entering deep sleep");
  ledcolor(0xff0000);  // RED
  delay(50);
  esp_deep_sleep(1000000LL * TIME_TO_SLEEP);
  // This line should never run so it's a canary for sleep failed
  rfhsledfatal();
}

void loop() {
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  rfhsledfatal();
}
