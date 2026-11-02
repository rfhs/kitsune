#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLEBeacon.h>
#include <rfhsbt.h>

// Exactly one difficulty, so exactly one block of the conference header
// defines the values below.
#if (defined(EASY) + defined(MEDIUM) + defined(HARD)) != 1
#error "Build with exactly one of -D EASY, -D MEDIUM or -D HARD"
#endif
// DEVICE_NAME travels in the 31 byte scan response. Bluedroid sends up to
// 29 characters as the complete name and anything longer truncated as a
// "short name", which would not match the report.
#ifndef DEVICE_NAME
#error "DEVICE_NAME must be defined in the conference header, a string of 1-29 characters"
#endif
static_assert(sizeof(DEVICE_NAME) - 1 >= 1 && sizeof(DEVICE_NAME) - 1 <= 29, "DEVICE_NAME must be 1-29 characters");
// BEACON_UUID must be the 36 character 8-4-4-4-12 form. BLEUUID logs an
// error and leaves the UUID unset for any other length, and the beacon
// goes out with garbage.
#ifndef BEACON_UUID
#error "BEACON_UUID must be defined in the conference header, \"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\""
#endif
static_assert(sizeof(BEACON_UUID) == 37 && rfhs_uuid_ok(BEACON_UUID),
    "BEACON_UUID must be 36 characters: 8-4-4-4-12 hex digits separated by hyphens");
// MAJOR and MINOR are the 16 bit iBeacon fields. SIGNAL_POWER is the
// calibrated RSSI at one metre as a signed byte; -59 and 0xC5 are the
// same value.
#ifndef MAJOR
#error "MAJOR must be defined in the conference header, 0-65535"
#elif MAJOR < 0 || MAJOR > 65535
#error "MAJOR must be 0-65535"
#endif
#ifndef MINOR
#error "MINOR must be defined in the conference header, 0-65535"
#elif MINOR < 0 || MINOR > 65535
#error "MINOR must be 0-65535"
#endif
#ifndef SIGNAL_POWER
#error "SIGNAL_POWER must be defined in the conference header, -128 to 127 dBm or the same as a byte 0x00-0xFF"
#elif SIGNAL_POWER < -128 || SIGNAL_POWER > 255
#error "SIGNAL_POWER must be -128 to 127, or 0x00-0xFF for the same value as a byte"
#endif
// An iBeacon always carries Apple's company identifier 0x004C. It is not a
// conference setting: a value in the header is discarded so nothing else
// can go on air.
#ifdef MANUFACTURER_ID
#undef MANUFACTURER_ID
#endif
// Byte swapped to 0x4C00, the form the library wants.
#define MANUFACTURER_ID 0x4C00

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

BLEAdvertising *pAdvertising;
BLEServer *pServer;
BLECharacteristic *pCharacteristic;
bool deviceConnected = false;
uint8_t value = 0;

void init_beacon() {
  // iBeacon
  BLEBeacon myBeacon;
  myBeacon.setManufacturerId(MANUFACTURER_ID);
  myBeacon.setMajor(MAJOR);
  myBeacon.setMinor(MINOR);
  myBeacon.setSignalPower((int8_t)SIGNAL_POWER);
  BLEUUID bleUUID = BLEUUID(BEACON_UUID);
  bleUUID = bleUUID.to128();
  myBeacon.setProximityUUID(BLEUUID(bleUUID.getNative()->uuid.uuid128, 16, true));
  BLEAdvertisementData advertisementData;
  advertisementData.setFlags(0x1A);
  advertisementData.setManufacturerData(myBeacon.getData());
  pAdvertising->setAdvertisementData(advertisementData);

}

void rfhsstartibeacon() {
  rfhssetbtmac();
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
}
