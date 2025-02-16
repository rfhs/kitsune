#include <Arduino.h>

#include "esp_sleep.h"
#include "sys/time.h"
#include "current_conf.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLEBeacon.h>

#include <rfhsledmacros.h>

// Edit the conference specific variables in a new file and symlink to current_conf.h
#if defined(EASY)

#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_P9

#elif defined(MEDIUM)

#define DEEP_SLEEP
#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_N0
#define ADVERTISING_DURATION     1  // time to remain advertising
#define GPIO_DEEP_SLEEP_DURATION 5  // sleep x seconds and then wake up

#elif defined(HARD)

#define DEEP_SLEEP
#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_N12
#define ADVERTISING_DURATION     10  // time to remain advertising
#define GPIO_DEEP_SLEEP_DURATION 30  // sleep x seconds and then wake up

#endif
//#MAX 40959ms
// ADV_TX_POWER   Power level for advertisements
// ---------------------------------------------
// ESP_PWR_LVL_N12 = 0 | Corresponding to -12dbm
// ESP_PWR_LVL_N9 = 1  | Corresponding to -9dbm
// ESP_PWR_LVL_N6 = 2  | Corresponding to -6dbm
// ESP_PWR_LVL_N3 = 3  | Corresponding to -3dbm
// ESP_PWR_LVL_N0 = 4  | Corresponding to  0dbm
// ESP_PWR_LVL_P3 = 5  | Corresponding to +3dbm
// ESP_PWR_LVL_P6 = 6  | Corresponding to +6dbm
// ESP_PWR_LVL_P9 = 7  | Corresponding to +9dbm
//#define ADV_TX_POWER        ESP_PWR_LVL_P9

// ADV_TYPE
// For non-connectable advertisements without device name, set to: ADV_TYPE_NONCONN_IND 
// For non-connectable advertisements with device name, set to: ADV_TYPE_SCAN_IND
#define ADV_TYPE            ADV_TYPE_SCAN_IND 

// Advertisement interval
// Defaults to MIN: 32 MAX: 64 which results in 43ms interval, easy to confirm with nRF Connect app.
// MIN: 400 MAX: 500 results in 315ms interval
// MIN: 5000 MAX: 6000 results in 4-7s interval

uint8_t mac_addr[6] = MAC_ADDR;

RTC_DATA_ATTR static time_t last;    // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
struct timeval now;

BLEAdvertising *pAdvertising;
BLEServer *pServer;
BLECharacteristic *pCharacteristic;
bool deviceConnected = false;
uint8_t value = 0;

void init_beacon() {
  // iBeacon
  BLEBeacon myBeacon;
  myBeacon.setManufacturerId(0x4c00);
  myBeacon.setMajor(5);
  myBeacon.setMinor(88);
  myBeacon.setSignalPower(0xc5);
  BLEUUID bleUUID = BLEUUID(BEACON_UUID);
  bleUUID = bleUUID.to128();
  myBeacon.setProximityUUID(BLEUUID(bleUUID.getNative()->uuid.uuid128, 16, true));
  BLEAdvertisementData advertisementData;
  advertisementData.setFlags(0x1A);
  advertisementData.setManufacturerData(myBeacon.getData());
  pAdvertising->setAdvertisementData(advertisementData);

}

void setup() {
  Serial.begin(115200);
  Serial.flush();
  Serial.println("Initializing...");
  rfhsledinit();
  gettimeofday(&now, NULL);
  Serial.printf("Start ESP32 %d\r\n", bootcount++);
  Serial.printf("deep sleep (%lds since last reset, %lds since last boot)\r\n", now.tv_sec, now.tv_sec - last);
  last = now.tv_sec;
  Serial.flush();

  // https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/misc_system_api.html#mac-address
  mac_addr[5] -= 2;
  esp_base_mac_addr_set(mac_addr);
  BLEDevice::init(DEVICE_NAME);
 
  BLEDevice::setPower(ADV_TX_POWER);

  pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->setAdvertisementType(ADV_TYPE);
  pAdvertising->setMinPreferred(0x0); 
  pAdvertising->setMinInterval(ADV_MIN_INTERVAL);
  pAdvertising->setMaxInterval(ADV_MAX_INTERVAL);

  //init_service();
  init_beacon();

  pAdvertising->start();
  ledcolor(0x0000FF); // BLUE
  Serial.println("iBeacon advertising!");
  #ifdef DEEP_SLEEP
  delay(ADVERTISING_DURATION * 1000);

  ledcolor(0x880000);  // HALF RED
  pAdvertising->stop();
  Serial.println("entering deep sleep");
  ledcolor(0xff0000);  // RED
  delay(50);
  esp_deep_sleep(1000000LL * GPIO_DEEP_SLEEP_DURATION);
  // This line should never run so it's a canary for sleep failed
  rfhsledfatal();
  #endif
}

void loop() {
  #ifdef DEEP_SLEEP
  // setup should sleep then restart so this should also never run.
  Serial.println("Entered loop, we are broken");
  rfhsledfatal();
  #endif
}
