// The serial line that identifies a fox: "Fox: <project> <DIFFICULTY>" with
// " <MODE>" appended for Wi-Fi, for example "Fox: wifi_ap_client EASY AP".
// The project is RFHS_PROJECT, the directory the firmware was built from,
// which main.cpp defines, and the other tokens come from the -D macros of
// the build environment. The verify scripts read this line to pick the block
// of current_conf.h to check against, and to tell a fox from any other
// device on the port.
//
// RFHS_BANNER is called right after the radio is up and right before the
// readback lines. Boards with native USB re-enumerate the serial device
// after deep sleep, and the time the radio takes to start is what lets the
// host reopen the port before the banner and the readback go out. A fox
// that fails before the banner prints it from rfhsfatal() instead, so the
// verify scripts still see a fox that halted rather than a device that is
// not a fox.
#pragma once
#include <Arduino.h>

#if defined(EASY)
#define RFHS_DIFFICULTY "EASY"
#elif defined(MEDIUM)
#define RFHS_DIFFICULTY "MEDIUM"
#elif defined(HARD)
#define RFHS_DIFFICULTY "HARD"
#elif defined(FIVEEASY)
#define RFHS_DIFFICULTY "FIVEEASY"
#elif defined(FIVEHARD)
#define RFHS_DIFFICULTY "FIVEHARD"
#else
#error "Build with a difficulty: -D EASY, -D MEDIUM, -D HARD, -D FIVEEASY or -D FIVEHARD"
#endif

#if defined(AP)
#define RFHS_MODE " AP"
#elif defined(CLIENT)
#define RFHS_MODE " CLIENT"
#else
#define RFHS_MODE ""
#endif

// Set once the banner has gone out; rfhsfatal() prints the banner first when
// it is still clear.
static bool rfhs_banner_printed = false;

// RFHS_PROJECT is a string literal, so the whole banner is one string in the
// firmware image and `strings firmware.elf | grep '^Fox: '` shows it.
void rfhsbanner() {
  Serial.println("Fox: " RFHS_PROJECT " " RFHS_DIFFICULTY RFHS_MODE);
  rfhs_banner_printed = true;
}

// Test hook: a build with -D RFHS_TEST_FATAL=<code> halts with that fatal
// code right after the banner, so each blink code can be watched on each
// board. No platformio.ini sets it.
#ifdef RFHS_TEST_FATAL
void rfhsfatal(int code);
#define RFHS_BANNER() do { rfhsbanner(); rfhsfatal(RFHS_TEST_FATAL); } while (0)
#else
#define RFHS_BANNER() rfhsbanner()
#endif
