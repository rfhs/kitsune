// What every fox does, apart from its radio: boot, the LED states, the
// banner, the wake, the sleep that keeps the cycle exact, and the fatal halt.
// main.cpp defines RFHS_PROJECT, includes this file and then its radio
// header, which provides rfhsstartradio(), rfhscheckradio(), rfhsstopradio()
// and RFHS_AWAKE_COLOR, and its setup() is the same twelve lines in every
// project.
#pragma once
#include <Arduino.h>
#ifndef RFHS_PROJECT
#error "define RFHS_PROJECT \"<project directory>\" in main.cpp before including rfhsfox.h"
#endif
#include <rfhsledmacros.h>
#include <rfhssleeptimers.h>
#include <rfhsbanner.h>

// The radio header defines these. rfhsstartradio() sets the MAC address and
// starts the radio, returning false when any step is refused;
// rfhscheckradio() prints every value read back from the stack, the device
// address first, and returns false when one differs from the conference
// header; rfhsstopradio() takes the radio off the air.
bool rfhsstartradio();
bool rfhscheckradio();
void rfhsstopradio();

// The fatal codes. rfhsfatal() prints the line of its code before PANIC and
// then blinks the LED red that many times, over and over, so a fox without
// a serial cable still says what went wrong.
#define RFHS_FATAL_RADIO 1     // the MAC set or the radio start was refused
#define RFHS_FATAL_READBACK 2  // a value read back from the stack differs from the header
#define RFHS_FATAL_SLEEP 3     // esp_deep_sleep() returned
#define RFHS_FATAL_LOOP 4      // loop() ran; setup() always ends in deep sleep
static const char *const rfhs_fatal_lines[] = {
  "Fatal 1: radio start failed",
  "Fatal 2: readback mismatch",
  "Fatal 3: deep sleep returned",
  "Fatal 4: loop() reached",
};
#if defined(RFHS_TEST_FATAL) && (RFHS_TEST_FATAL < 1 || RFHS_TEST_FATAL > 4)
#error "RFHS_TEST_FATAL must be a fatal code, 1-4"
#endif

// The seconds rfhsawake() was given, for rfhssleep() to complete the cycle.
static unsigned rfhs_wake_seconds;

// The first lines of setup(): serial, the boot LED, the boot timer and
// "Setting up <what>...", where what names the radio, "WiFi AP" say.
void rfhsboot(const char *what) {
  Serial.begin(115200);
  Serial.flush();
  rfhsledinit();
  Serial.println("Initializing...");
  rfhsboottimer();
  Serial.printf("Setting up %s...\r\n", what);
}

// Reports the result of the radio's MAC address set and hands it back, so
// rfhsstartradio() stops on a failure.
bool rfhsmacset(bool ok) {
  Serial.println(ok ? "MAC address set successfully" : "Error setting MAC address");
  return ok;
}

// On the air for seconds.
void rfhsawake(unsigned seconds) {
  Serial.println("Awake and screaming");
  rfhs_wake_seconds = seconds;
  delay(seconds * 1000UL);
}

// Halts the fox. The radio goes off first, so a halted fox never transmits
// something the report does not say; the banner is printed when it has not
// gone out yet, so the verify scripts see a fox that halted.
void rfhsfatal(int code) {
  Serial.flush();
  rfhsstopradio();
  if (!rfhs_banner_printed) {
    rfhsbanner();
  }
  Serial.println(rfhs_fatal_lines[code - 1]);
  Serial.println("PANIC");
  Serial.flush();
  rfhsledrelease();
  while (true) {
    rfhsledblink(code);
  }
}

// Deep sleep until the cycle that began at this boot is exactly
// rfhs_wake_seconds + seconds long. The radio is already off. esp_deep_sleep()
// never returns, so the line after it is the sleep canary.
void rfhssleep(unsigned seconds) {
  Serial.println("Going to sleep");
  rfhsled(RFHS_LED_SLEEP);
  // The WS2812 latches a colour 50 us after its data ends.
  delay(5);
  int64_t sleep_us = rfhssleepmicros(rfhs_wake_seconds, seconds);
  Serial.flush();
  rfhsledhold();
  esp_deep_sleep((uint64_t)sleep_us);
  rfhsfatal(RFHS_FATAL_SLEEP);
}
