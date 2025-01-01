#include <FastLED.h>

#define NUM_LEDS 1
#define DATA_PIN 27
// This is for atoms3-lite
//#define DATA_PIN 35
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
}
