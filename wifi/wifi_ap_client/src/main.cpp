#include <Arduino.h>
#include "current_conf.h"
#define RFHS_PROJECT "wifi_ap_client"
#include <rfhsfox.h>
#include <rfhswifi.h>

void setup() {
#if defined(AP)
  rfhsboot("WiFi AP");
#else
  rfhsboot("WiFi Client");
#endif
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
