#include <Arduino.h>
#include "current_conf.h"
#define RFHS_PROJECT "iBeacon"
#include <rfhsfox.h>
#include <rfhsibeacon.h>

void setup() {
  rfhsboot("iBeacon");
  rfhsled(RFHS_LED_AWAKE);
  if (!rfhsstartradio()) {
    rfhsfatal(RFHS_FATAL_RADIO);
  }
  RFHS_BANNER();
  rfhsprintsleeptimers();
  if (!rfhscheckradio()) {
    rfhsfatal(RFHS_FATAL_READBACK);
  }
  rfhsawake(TIME_TO_WAKE);
  rfhsstopradio();
  rfhssleep(TIME_TO_SLEEP);
}

void loop() {
  rfhsfatal(RFHS_FATAL_LOOP);
}
