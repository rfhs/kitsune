#include <FastLED.h>

#define NUM_LEDS 1

#if defined(ARDUINO_M5Stack_ATOM)
#define DATA_PIN 27
#elif defined(ARDUINO_M5Stack_ATOMS3)
#define DATA_PIN 35
#elif defined(ARDUINO_M5Stick_C)
#define DATA_PIN 19
#elif defined(ARDUINO_M5Stack_StampS3)
#define DATA_PIN 21
#endif

CRGB leds[NUM_LEDS];

void ledcolor(uint32_t colorcode) {
  /*
   * What if we had more than 1 led?
   * for(int num=0; num<NUM_LEDS; num++) {
   *  leds[num] = CRGB(colorcode);
   * }
   */

  leds[0] = CRGB(colorcode);
  FastLED.show();
  // We are supposed to wait this long but I don't want to.
  // delay(50)
}

void rfhsledinit() {
  FastLED.addLeds<WS2812, DATA_PIN, GRB>(leds, NUM_LEDS);
  // M5Stack recommends not setting this value greater than 20
  // to avoid melting the screen/cover over the LEDs
  FastLED.setBrightness(20);
  // Set a color so we know the leds have been initialized
  ledcolor(0x9400D3);  // DARKVIOLET
}

void rfhsledfatal() {
  while (1) {
    ledcolor(0xff0000);  // RED
    delay(200);
    ledcolor(0xFFF700);  // Yellow
    delay(200);
  }
}
