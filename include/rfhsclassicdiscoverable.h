#include "BluetoothSerial.h"
#include <rfhsbt.h>

// This check seems wrong because it passes on hardware which doesn't support BT Classic
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
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
