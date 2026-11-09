#include <stdio.h>
#include <string.h>
#include <esp_bt.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLEBeacon.h>
#include <type_traits>
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
// TIME_TO_WAKE is the seconds the beacon is on the air per wake. An active
// scan needs to hear the beacon and then get its name from a scan response,
// so a shorter window lets a scan miss the fox or see it without the name.
// rfhssleeptimers.h checks the upper bound and TIME_TO_SLEEP.
#if TIME_TO_WAKE < 5
#error "TIME_TO_WAKE must be at least 5 seconds so an active scan can hear the beacon and read its name"
#endif
// TXPOWER is one of the ESP_PWR_LVL_* names. Only the eight levels both
// supported cores define are allowed, ESP_PWR_LVL_N12 to ESP_PWR_LVL_P9 in
// 3 dBm steps, and only under those names: the ESP32-S3 core has lower and
// higher names the ESP32 core lacks, and the ESP32 core has aliases such as
// ESP_PWR_LVL_N14 that stand for another level, which the controller would
// report under that level's name. An alias has the same number as the level
// it stands for, so the text of the value is compared, not its number.
#ifndef TXPOWER
#error "TXPOWER must be defined in the conference header, an ESP_PWR_LVL_* name from ESP_PWR_LVL_N12 to ESP_PWR_LVL_P9"
#endif
static_assert(std::is_same<decltype(TXPOWER), esp_power_level_t>::value, "TXPOWER must be an ESP_PWR_LVL_* name, not a number");
static_assert(rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_N12") || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_N9")
           || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_N6") || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_N3")
           || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_N0") || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_P3")
           || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_P6") || rfhs_str_eq(RFHS_STR(TXPOWER), "ESP_PWR_LVL_P9"),
    "TXPOWER must be one of ESP_PWR_LVL_N12, ESP_PWR_LVL_N9, ESP_PWR_LVL_N6, ESP_PWR_LVL_N3, ESP_PWR_LVL_N0, ESP_PWR_LVL_P3, ESP_PWR_LVL_P6 or ESP_PWR_LVL_P9");

#define ADV_MIN_INTERVAL    32
#define ADV_MAX_INTERVAL    64

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
 
  BLEDevice::setPower(TXPOWER);
  // The advertising power type is set on its own as well, so the readback
  // of that type in rfhscheckibeacon() asks the controller for a value it
  // was given.
  BLEDevice::setPower(TXPOWER, ESP_BLE_PWR_TYPE_ADV);

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
// the transmit power are read back from the controller.
//
// The ESP_PWR_LVL_* names spell out a level's dBm, 3 dBm per step around
// ESP_PWR_LVL_N0 on the ESP32 and the ESP32-S3, so the name of any level the
// controller reports is built from that number.
static int rfhsbledbm(esp_power_level_t level) {
  return 3 * ((int)level - (int)ESP_PWR_LVL_N0);
}

static const char *rfhsblepowername(esp_power_level_t level, char *name, size_t size) {
  int dbm = rfhsbledbm(level);
  snprintf(name, size, "ESP_PWR_LVL_%c%d", dbm > 0 ? 'P' : 'N', dbm < 0 ? -dbm : dbm);
  return name;
}

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
  char name[24];
  Serial.printf("Tx power: %s (%d dBm)\r\n",
      rfhsblepowername(level, name, sizeof(name)), rfhsbledbm(level));
  if (level != TXPOWER) {
    Serial.printf("Requested tx power: %s (%d dBm)\r\n",
        rfhsblepowername(TXPOWER, name, sizeof(name)), rfhsbledbm(TXPOWER));
    Serial.println("Tx power != Requested tx power");
    return false;
  }
  return true;
}
