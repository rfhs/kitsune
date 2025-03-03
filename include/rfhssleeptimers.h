#include "esp_sleep.h"
#include "sys/time.h"

// microseconds are used by esp_sleep_enable_timer_wakeup
#define uS_TO_S 1000000
// milliseconds are used by delay
#define mS_TO_S 1000

RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
struct timeval now;

void rfhsboottimer() {
  gettimeofday(&now, NULL);
  Serial.printf("ESP32 boot count: %d\r\n", bootcount++);
  Serial.printf("Sleep stats: %lds since cold boot, %lds since last wakeup\r\n", now.tv_sec, now.tv_sec - last);
  last = now.tv_sec;
}
