#include <Arduino.h>

#include "current_conf.h"
#include <rfhssleeptimers.h>
#include <rfhsledmacros.h>
#include <rfhszigbee.h>

void setup() {
  // Bring up serial early so we can debug
  Serial.begin(115200);
  Serial.flush();

  // Before this desired mac address is not set
  // Speed counts
  if (rfhssetzigbeemac()) {
    Serial.println("MAC address set successfully");
  } else {
    Serial.println("Error setting MAC address");
  }

  rfhsledinit();

  Serial.flush();
  Serial.println();
  Serial.println("Initializing...");
  rfhsboottimer();

  Serial.println("Setting up Zigbee Coordinator…");
  if (!rfhsstartzigbee() || !rfhscheckzigbee()) {
    Serial.flush();
    disableZigbee();
    rfhsledfatal();
  }
  Serial.flush();
  ledcolor(0x00ffff); // CYAN

  Serial.println("Awake and screaming");
  delay(TIME_TO_WAKE * mS_TO_S);
  Serial.println("Going to sleep");
  ledcolor(0x880000);  // HALF RED
  disableZigbee();
  ledcolor(0xff0000);  // RED
  delay(75); // Give the led time to set before sleeping
  // subtract sleep time on line 43
  int sleepy_tyme = uS_TO_S * TIME_TO_SLEEP - 75;
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
