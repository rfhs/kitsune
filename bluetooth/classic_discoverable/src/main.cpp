#include <Arduino.h>

#include "current_conf.h"
#include <rfhsledmacros.h>
#include <rfhssleeptimers.h>
#include <rfhsclassicdiscoverable.h>

void setup() {
  Serial.begin(115200);
  rfhsledinit();
  Serial.println("Initializing...");
  rfhsboottimer();

  rfhsstartclassicdiscoverable();

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
