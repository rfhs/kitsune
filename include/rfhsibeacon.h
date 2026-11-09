#include <stdio.h>
#include <string.h>
#include <esp_bt.h>
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

#if defined(EASY)

#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_P9

#elif defined(MEDIUM)

#define DEEP_SLEEP
#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_N0
// Seconds on air per wake and seconds asleep between wakes. Both can be
// overridden with a -D build flag.
#ifndef ADVERTISING_DURATION
#define ADVERTISING_DURATION     5
#endif
#ifndef GPIO_DEEP_SLEEP_DURATION
#define GPIO_DEEP_SLEEP_DURATION 5
#endif

#elif defined(HARD)

#define DEEP_SLEEP
#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64
#define ADV_TX_POWER        ESP_PWR_LVL_N12
// Seconds on air per wake and seconds asleep between wakes. Both can be
// overridden with a -D build flag.
#ifndef ADVERTISING_DURATION
#define ADVERTISING_DURATION     10
#endif
#ifndef GPIO_DEEP_SLEEP_DURATION
#define GPIO_DEEP_SLEEP_DURATION 30
#endif

#endif
// A sleeping fox is only on air for ADVERTISING_DURATION seconds per wake.
// An active scan needs the beacon to be heard and then answer a scan
// request with its name, so a shorter window lets a scan miss the fox or
// see it without the name.
#ifdef DEEP_SLEEP
#if ADVERTISING_DURATION < 5
#error "ADVERTISING_DURATION must be at least 5 seconds when DEEP_SLEEP is defined, so an active scan can hear the beacon and read its name"
#endif
#endif
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

// ADV_TYPE
// For non-connectable advertisements without device name, set to: ADV_TYPE_NONCONN_IND 
// For non-connectable advertisements with device name, set to: ADV_TYPE_SCAN_IND
#define ADV_TYPE            ADV_TYPE_SCAN_IND 

// Advertisement interval
// Defaults to MIN: 32 MAX: 64 which results in 43ms interval, easy to confirm with nRF Connect app.
// MIN: 400 MAX: 500 results in 315ms interval
// MIN: 5000 MAX: 6000 results in 4-7s interval

BLEAdvertising *pAdvertising;
// The manufacturer data block of the advertisement; rfhscheckibeacon()
// reads it back after it has been handed to the stack.
BLEBeacon myBeacon;

void init_beacon() {
  // iBeacon
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
  // The advertising power type is set on its own as well, so the readback
  // of that type in rfhscheckibeacon() asks the controller for a value it
  // was given.
  BLEDevice::setPower(ADV_TX_POWER, ESP_BLE_PWR_TYPE_ADV);

  pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->setAdvertisementType(ADV_TYPE);
  pAdvertising->setMinPreferred(0x0); 
  pAdvertising->setMinInterval(ADV_MIN_INTERVAL);
  pAdvertising->setMaxInterval(ADV_MAX_INTERVAL);

  init_beacon();

  pAdvertising->start();
}

// Prints what the beacon transmits and refuses to run when any of it
// differs from the conference header. Bluedroid in Arduino core 2.x
// returns the device name only through a GAP callback event, so the
// configured DEVICE_NAME is printed. The stack has no call that returns
// the advertisement, so the UUID, major, minor and signal power are read
// back from the manufacturer data handed to it, which has the iBeacon
// layout: company id, type, length, 16 byte UUID, major, minor and signal
// power, the 16 bit fields most significant byte first. The address and
// the advertising power are read back from the controller. Power levels
// are 3 dBm apart around ESP_PWR_LVL_N0 on the ESP32 and the ESP32-S3.
bool rfhscheckibeacon() {
  Serial.println("Device name: " DEVICE_NAME);
  std::string data = myBeacon.getData();
  if (data.size() != 25) {
    Serial.printf("Beacon data is %u bytes, not 25\r\n", (unsigned)data.size());
    return false;
  }
  const uint8_t *d = (const uint8_t *)data.data();
  char uuid[37];
  snprintf(uuid, sizeof(uuid),
      "%02X%02X%02X%02X-%02X%02X-%02X%02X-%02X%02X-%02X%02X%02X%02X%02X%02X",
      d[4], d[5], d[6], d[7], d[8], d[9], d[10], d[11],
      d[12], d[13], d[14], d[15], d[16], d[17], d[18], d[19]);
  Serial.printf("Beacon UUID: %s\r\n", uuid);
  if (strcasecmp(uuid, BEACON_UUID) != 0) {
    Serial.println("Requested UUID: " BEACON_UUID);
    Serial.println("Beacon UUID != Requested UUID");
    return false;
  }
  unsigned major = ((unsigned)d[20] << 8) | d[21];
  Serial.printf("Major: 0x%04X (%u)\r\n", major, major);
  if (major != (unsigned)MAJOR) {
    Serial.printf("Requested major: 0x%04X (%u)\r\n", (unsigned)MAJOR, (unsigned)MAJOR);
    Serial.println("Major != Requested major");
    return false;
  }
  unsigned minor = ((unsigned)d[22] << 8) | d[23];
  Serial.printf("Minor: 0x%04X (%u)\r\n", minor, minor);
  if (minor != (unsigned)MINOR) {
    Serial.printf("Requested minor: 0x%04X (%u)\r\n", (unsigned)MINOR, (unsigned)MINOR);
    Serial.println("Minor != Requested minor");
    return false;
  }
  int power = (int8_t)d[24];
  Serial.printf("Signal power: %d\r\n", power);
  if (power != (int)(int8_t)SIGNAL_POWER) {
    Serial.printf("Requested signal power: %d\r\n", (int)(int8_t)SIGNAL_POWER);
    Serial.println("Signal power != Requested signal power");
    return false;
  }
  BLEAddress address = BLEDevice::getAddress();
  if (!rfhscheckbtaddress(*address.getNative())) {
    return false;
  }
  esp_power_level_t level = esp_ble_tx_power_get(ESP_BLE_PWR_TYPE_ADV);
  Serial.printf("Advertising power: %d dBm (level %d)\r\n",
      3 * ((int)level - (int)ESP_PWR_LVL_N0), (int)level);
  if (level != ADV_TX_POWER) {
    Serial.printf("Requested advertising power: %d dBm (level %d)\r\n",
        3 * ((int)ADV_TX_POWER - (int)ESP_PWR_LVL_N0), (int)ADV_TX_POWER);
    Serial.println("Advertising power != Requested advertising power");
    return false;
  }
  return true;
}
