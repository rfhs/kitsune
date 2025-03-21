#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLEBeacon.h>
#include <rfhsbt.h>

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
