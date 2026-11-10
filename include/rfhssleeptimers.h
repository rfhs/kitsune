#pragma once
#include <Arduino.h>
#include "esp_sleep.h"
#include "sys/time.h"
#include <inttypes.h>

// TIME_TO_WAKE is the seconds a fox is on the air and TIME_TO_SLEEP the
// seconds it is off the air; one cycle, wake-up to wake-up, is exactly
// TIME_TO_WAKE + TIME_TO_SLEEP, because rfhssleepmicros() below shortens each
// sleep by the time the boot and the checks took. TIME_TO_SLEEP 0 reboots as
// soon as the wake is over. The ceilings are the largest values whose
// milliseconds, or microseconds, fit a signed 32 bit count.
#ifndef TIME_TO_WAKE
#error "TIME_TO_WAKE must be defined in the conference header, seconds awake, at least 1"
#elif TIME_TO_WAKE < 1 || TIME_TO_WAKE > 2147483
#error "TIME_TO_WAKE must be 1-2147483 seconds"
#endif
#ifndef TIME_TO_SLEEP
#error "TIME_TO_SLEEP must be defined in the conference header, seconds asleep, 0 or more"
#elif TIME_TO_SLEEP < 0 || TIME_TO_SLEEP > 2147
#error "TIME_TO_SLEEP must be 0-2147 seconds"
#endif
// Prints both timers for the verify scripts. They are compile time constants
// that main.cpp hands to rfhsawake() and rfhssleep(), so the configured
// values are printed; there is no stack to read them back from.
void rfhsprintsleeptimers() {
  Serial.printf("Time to wake: %ds\r\n", TIME_TO_WAKE);
  Serial.printf("Time to sleep: %ds\r\n", TIME_TO_SLEEP);
}

// Everything in RTC memory keeps its value through deep sleep and is reset
// by a power cycle or the reset button.
RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
// When this cycle and the previous one began, in microseconds of
// gettimeofday(). The system clock is kept by the RTC counter, which runs
// through deep sleep, so a stamp taken before a sleep and the clock read
// after it are on one time line. A cycle that a timer wake-up begins starts
// at the moment the timer was due, which rfhssleepmicros() stored before the
// sleep; any other boot starts a cycle when rfhsboottimer() runs.
RTC_DATA_ATTR static int64_t cycle_start;
RTC_DATA_ATTR static int64_t cycle_previous;
struct timeval now;

static int64_t rfhsmicros() {
  struct timeval tv;
  gettimeofday(&tv, NULL);
  return (int64_t)tv.tv_sec * 1000000 + tv.tv_usec;
}

void rfhsboottimer() {
  gettimeofday(&now, NULL);
  // time_t is 32 bit on the ESP32 cores and 64 bit on the ESP32-C5, so the
  // values are widened to long long for one format that fits both.
  Serial.printf("ESP32 boot count: %" PRIu32 "\r\n", bootcount++);
  Serial.printf("Sleep stats: %llds since cold boot, %llds since last wakeup\r\n",
      (long long)now.tv_sec, (long long)(now.tv_sec - last));
  last = now.tv_sec;
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER) {
    Serial.printf("Last cycle: %.1fs, target %ds\r\n",
        (cycle_start - cycle_previous) / 1e6, TIME_TO_WAKE + TIME_TO_SLEEP);
  } else {
    cycle_start = rfhsmicros();
  }
}

// The microseconds to sleep so the next wake-up comes exactly wake + sleep
// seconds after this cycle began, and the stamps for the next boot. A cycle
// that has already run past its end, which every TIME_TO_SLEEP 0 fox does by
// design, sleeps for 0 microseconds, which reboots at once.
int64_t rfhssleepmicros(unsigned wake, unsigned sleep) {
  int64_t target = cycle_start + (int64_t)(wake + sleep) * 1000000;
  int64_t now_us = rfhsmicros();
  int64_t sleep_us = target - now_us;
  if (sleep_us < 0) {
    if (sleep > 0) {
      Serial.printf("Cycle behind by %.1fs, rebooting at once\r\n", -sleep_us / 1e6);
    }
    target = now_us;
    sleep_us = 0;
  }
  cycle_previous = cycle_start;
  cycle_start = target;
  return sleep_us;
}
