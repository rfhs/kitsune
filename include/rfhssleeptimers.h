#include "esp_sleep.h"
#include "sys/time.h"
#include <inttypes.h>

// microseconds are used by esp_sleep_enable_timer_wakeup
#define uS_TO_S 1000000
// milliseconds are used by delay
#define mS_TO_S 1000

// Foxes that sleep define both. main.cpp computes TIME_TO_WAKE * mS_TO_S
// and uS_TO_S * TIME_TO_SLEEP in int, so the ceilings are where that
// arithmetic would overflow. TIME_TO_SLEEP 0 reboots as soon as the wake
// is over.
#if defined(TIME_TO_WAKE) || defined(TIME_TO_SLEEP)
#ifndef TIME_TO_WAKE
#error "TIME_TO_WAKE must be defined alongside TIME_TO_SLEEP, seconds awake, at least 1"
#elif TIME_TO_WAKE < 1 || TIME_TO_WAKE > 2147483
#error "TIME_TO_WAKE must be 1-2147483 seconds"
#endif
#ifndef TIME_TO_SLEEP
#error "TIME_TO_SLEEP must be defined alongside TIME_TO_WAKE, seconds asleep, 0 or more"
#elif TIME_TO_SLEEP < 0 || TIME_TO_SLEEP > 2147
#error "TIME_TO_SLEEP must be 0-2147 seconds"
#endif
#endif

RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
struct timeval now;

void rfhsboottimer() {
  gettimeofday(&now, NULL);
  // time_t is 32 bit on the ESP32 cores and 64 bit on the ESP32-C5, so the
  // values are widened to long long for one format that fits both.
  Serial.printf("ESP32 boot count: %" PRIu32 "\r\n", bootcount++);
  Serial.printf("Sleep stats: %llds since cold boot, %llds since last wakeup\r\n",
      (long long)now.tv_sec, (long long)(now.tv_sec - last));
  last = now.tv_sec;
}
