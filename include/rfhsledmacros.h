#include <FastLED.h>

const uint8_t ESP32_MAX_BRIGHTNESS = 20;

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

#if defined(ARDUINO_NANO_ESP32)

  //Adjusting Brightness
  leds[0].nscale8(ESP32_MAX_BRIGHTNESS);

  //Displaying the color on the board
  analogWrite(LED_RED,   255 - leds[0].r);
  analogWrite(LED_GREEN, 255 - leds[0].g);
  analogWrite(LED_BLUE,  255 - leds[0].b);


#else

  // For any digital LED
  FastLED.show();

  // We are supposed to wait this long but I don't want to.
  // delay(50)

#endif
}

void rfhsledinit() {

#if defined(ARDUINO_NANO_ESP32)

// Basically do nothing. The colors are set in ledcolor()

// #elif defined(ARDUINO_XIAO_ESP32C5)
  // Single yellow LED on GPIO 27 as output
  // pinMode(27, OUTPUT);

#else
  FastLED.addLeds<WS2812, DATA_PIN, GRB>(leds, NUM_LEDS);
  // M5Stack recommends not setting this value greater than 20
  // to avoid melting the screen/cover over the LEDs
  FastLED.setBrightness(20);
#endif
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
