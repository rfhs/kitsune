#include "BluetoothSerial.h"
#include <rfhsbt.h>

// Only the original ESP32 has a BR/EDR controller, and only its core
// defines CONFIG_BT_CLASSIC_ENABLED. CONFIG_BT_ENABLED and
// CONFIG_BLUEDROID_ENABLED are set for the ESP32-S3 as well, so they do
// not tell the chips apart.
#ifndef CONFIG_BT_CLASSIC_ENABLED
#error "Bluetooth Classic needs the original ESP32; this chip's core has no BR/EDR controller"
#endif

// Exactly one difficulty, so exactly one block of the conference header
// defines the values below.
#if (defined(EASY) + defined(HARD)) != 1
#error "Build with exactly one of -D EASY or -D HARD"
#endif
// NAME is the Bluetooth Classic device name hunters see. The core is built
// with CONFIG_BT_MAX_DEVICE_NAME_LEN 32, and esp_bt_dev_set_device_name
// rejects a longer name, so the fox would advertise the library default.
#ifndef NAME
#error "NAME must be defined in the conference header, a string of 1-32 characters"
#endif
static_assert(sizeof(NAME) - 1 >= 1 && sizeof(NAME) - 1 <= 32, "NAME must be 1-32 characters");
// A general inquiry takes 10.24 seconds and the fox answers about 2 seconds
// after it boots, so a shorter wake can end before an inquiry that started
// as the fox woke has reached it. rfhssleeptimers.h checks the upper bound.
#if TIME_TO_WAKE < 15
#error "TIME_TO_WAKE must be at least 15 seconds: a Bluetooth inquiry takes 10.24 seconds and the fox needs about 2 seconds after boot to answer one"
#endif

BluetoothSerial SerialBT;

void rfhssetbtclassicname() {
  // String localName=String(), bool isMaster=false
  SerialBT.begin(NAME, false); //Bluetooth device name
}

void rfhsstartclassicdiscoverable() {
  rfhssetbtmac();
  rfhssetbtclassicname();
}

// Prints the name and address hunters see and refuses to run when the
// address differs from the conference header. Bluedroid in Arduino core
// 2.x has no call that returns the Classic device name, so the configured
// NAME is printed; the address is read back from the stack.
bool rfhscheckclassicdiscoverable() {
  Serial.println("Device name: " NAME);
  return rfhscheckbtaddress(esp_bt_dev_get_address());
}
