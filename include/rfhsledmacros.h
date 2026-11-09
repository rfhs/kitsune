// The LED of a fox: one steady colour per state and a counted red blink for
// a fatal error. The M5Stack boards have a WS2812 that FastLED drives, the
// Arduino Nano ESP32 has an RGB LED on three active low PWM pins, and the
// XIAO ESP32-C5 has one active low LED, which shows off, on and blinking.
#pragma once
#include <Arduino.h>
#include <FastLED.h>
#include <driver/gpio.h>

#define NUM_LEDS 1

// The WS2812 data pin, or the pin of the XIAO ESP32-C5's one LED. The Nano's
// three pins are LED_RED, LED_GREEN and LED_BLUE from its variant.
#if defined(ARDUINO_M5Stack_ATOM)
#define DATA_PIN 27
#elif defined(ARDUINO_M5Stack_ATOMS3)
#define DATA_PIN 35
#elif defined(ARDUINO_M5Stack_StampS3)
#define DATA_PIN 21
#elif defined(ARDUINO_XIAO_ESP32C5)
#define DATA_PIN 27
#elif !defined(ARDUINO_NANO_ESP32)
#error "add this board's LED pin to include/rfhsledmacros.h"
#endif

// The three steady states. Boot is dark violet from the first line of
// setup() until the radio is switched on, awake is the radio's colour while
// the fox is on the air, and asleep is red, which the WS2812 boards and the
// Nano keep showing through deep sleep. The XIAO ESP32-C5's one LED is off
// while booting and asleep and on while on the air.
enum rfhsledstate { RFHS_LED_BOOT, RFHS_LED_AWAKE, RFHS_LED_SLEEP };
#define RFHS_BOOT_COLOR 0x9400D3
#define RFHS_SLEEP_COLOR 0xFF0000
#define RFHS_FATAL_COLOR 0xFF0000
// The awake colour is the radio's, one colour per radio so a box tells
// which fox it is. Each radio header defines RFHS_AWAKE_COLOR and sets this
// constant from it; main.cpp includes the radio header after rfhsfox.h, so
// rfhsled() reaches the value through the constant.
extern const uint32_t rfhs_awake_color;

CRGB leds[NUM_LEDS];

// Writes one colour. On the XIAO ESP32-C5 black is off and any other colour
// is on, so the dark phase of a blink is the same code on every board.
void ledcolor(uint32_t colorcode) {
  leds[0] = CRGB(colorcode);
#if defined(ARDUINO_NANO_ESP32)
  // The brightness has to be applied on every write. The LED is active low,
  // so the PWM duty is inverted.
  leds[0].nscale8(75);
  analogWrite(LED_RED,   255 - leds[0].r);
  analogWrite(LED_GREEN, 255 - leds[0].g);
  analogWrite(LED_BLUE,  255 - leds[0].b);
#elif defined(ARDUINO_XIAO_ESP32C5)
  digitalWrite(DATA_PIN, colorcode == 0x000000 ? HIGH : LOW);
#else
  FastLED.show();
#endif
}

// Shows a state.
void rfhsled(rfhsledstate state) {
#if defined(ARDUINO_XIAO_ESP32C5)
  ledcolor(state == RFHS_LED_AWAKE ? rfhs_awake_color : 0x000000);
#elif defined(ARDUINO_NANO_ESP32)
  if (state == RFHS_LED_SLEEP) {
    // The sleep state is written as plain levels, red on and the other two
    // off, because the pads are held at these levels through deep sleep and
    // the PWM behind ledcolor() stops with the chip.
    pinMode(LED_RED, OUTPUT);
    digitalWrite(LED_RED, LOW);
    pinMode(LED_GREEN, OUTPUT);
    digitalWrite(LED_GREEN, HIGH);
    pinMode(LED_BLUE, OUTPUT);
    digitalWrite(LED_BLUE, HIGH);
    return;
  }
  ledcolor(state == RFHS_LED_BOOT ? RFHS_BOOT_COLOR : rfhs_awake_color);
#else
  if (state == RFHS_LED_BOOT) {
    ledcolor(RFHS_BOOT_COLOR);
  } else if (state == RFHS_LED_AWAKE) {
    ledcolor(rfhs_awake_color);
  } else {
    ledcolor(RFHS_SLEEP_COLOR);
  }
#endif
}

// Holds the pads that show the sleep state through deep sleep, so a sleeping
// XIAO ESP32-C5 is dark and a sleeping Nano is red. The WS2812 boards need
// nothing: the LED keeps its last colour as long as it has power.
void rfhsledhold() {
#if defined(ARDUINO_XIAO_ESP32C5)
  // The ESP32-C5 keeps a single pad's hold through deep sleep on its own.
  gpio_hold_en((gpio_num_t)DATA_PIN);
#elif defined(ARDUINO_NANO_ESP32)
  // LED_RED and LED_BLUE are digital pads of the ESP32-S3, which keep their
  // hold through deep sleep only with gpio_deep_sleep_hold_en(); LED_GREEN
  // is an RTC pad and keeps it on its own. The variant numbers the pins the
  // Arduino way, so they are mapped to GPIO numbers for the driver.
  gpio_hold_en((gpio_num_t)digitalPinToGPIONumber(LED_RED));
  gpio_hold_en((gpio_num_t)digitalPinToGPIONumber(LED_GREEN));
  gpio_hold_en((gpio_num_t)digitalPinToGPIONumber(LED_BLUE));
  gpio_deep_sleep_hold_en();
#endif
}

// Releases the holds of rfhsledhold(), so the pads follow the LED writes
// again after a wake-up.
void rfhsledrelease() {
#if defined(ARDUINO_XIAO_ESP32C5)
  gpio_hold_dis((gpio_num_t)DATA_PIN);
#elif defined(ARDUINO_NANO_ESP32)
  gpio_deep_sleep_hold_dis();
  gpio_hold_dis((gpio_num_t)digitalPinToGPIONumber(LED_RED));
  gpio_hold_dis((gpio_num_t)digitalPinToGPIONumber(LED_GREEN));
  gpio_hold_dis((gpio_num_t)digitalPinToGPIONumber(LED_BLUE));
#endif
}

// Sets the LED up and shows the boot state.
void rfhsledinit() {
  rfhsledrelease();
#if defined(ARDUINO_NANO_ESP32)
  // The pins are configured by analogWrite() in ledcolor().
#elif defined(ARDUINO_XIAO_ESP32C5)
  pinMode(DATA_PIN, OUTPUT);
#else
  FastLED.addLeds<WS2812, DATA_PIN, GRB>(leds, NUM_LEDS);
  // M5Stack recommends no more than 20, so the cover over the LED does not
  // melt.
  FastLED.setBrightness(20);
#endif
  rfhsled(RFHS_LED_BOOT);
}

// Blinks red n times, 250 ms on and 250 ms off, then stays dark for 1.5 s.
// rfhsfatal() repeats it forever with its code as n.
void rfhsledblink(int n) {
  for (int i = 0; i < n; i++) {
    ledcolor(RFHS_FATAL_COLOR);
    delay(250);
    ledcolor(0x000000);
    delay(250);
  }
  delay(1500);
}
