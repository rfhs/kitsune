// The serial line that identifies a fox: "Fox: <project> <DIFFICULTY>" with
// " <MODE>" appended for Wi-Fi, for example "Fox: wifi_ap_client EASY AP".
// The project is the directory the firmware was built from and the other
// tokens come from the -D macros of the build environment. The verify
// scripts read this line to pick the block of current_conf.h to check
// against, and to tell a fox from any other device on the port.
//
// RFHS_BANNER is called right after the radio is up and right before the
// readback lines. Boards with native USB re-enumerate the serial device
// after deep sleep, and the time the radio takes to start is what lets the
// host reopen the port before the banner and the readback go out.
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

// project is a string literal, so the whole banner is one string in the
// firmware image and `strings firmware.elf | grep '^Fox: '` shows it.
#define RFHS_BANNER(project) Serial.println("Fox: " project " " RFHS_DIFFICULTY RFHS_MODE)
