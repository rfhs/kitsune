RF CTF Fox code

[![Build Test All](https://github.com/rfhs/kitsune/actions/workflows/build-test-all.yaml/badge.svg)](https://github.com/rfhs/kitsune/actions/workflows/build-test-all.yaml)


|Hardware |Bluetooth iBeacon |Bluetooth Classic Discoverable |Wifi AP |Client |
|------------------- | :---------: | :------: | :---------------------------: | :-----: |
|M5Stack Atom-lite |✅|✅|✅|✅|
|M5Stack AtomS3-lite |✅|❌|✅|✅|
|M5Stack StampS3 |✅|❌|✅|✅|
|Arduino Nano ESP32 |✅|❌|✅|❌|
|Seeed XIAO ESP32C5 |❌|❌|✅|❌||

We will accept PRs to extend support to other platformio supported hardware.

We have powered our foxes using these batteries:
- https://www.amazon.com/dp/B0C8G8Y3JF
- https://www.amazon.com/dp/B0D2L2Z6VQ

You can use any battery you like, as long as it supplies 5v and does NOT have a low power cut off.  Batteries meant for charging things like cell phones automatically turn off when the draw is low, this means when the esp32 takes a short sleep cycle it never wakes up.
