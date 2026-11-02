#include <WiFi.h>
#include <esp_wifi.h>
#include <type_traits>
#include <rfhsconfcheck.h>

// Exactly one mode and exactly one difficulty, so exactly one block of the
// conference header defines the values below. The 5 GHz difficulties stand
// alone; a build must not also define EASY or HARD with them.
#if (defined(AP) + defined(CLIENT)) != 1
#error "Build with exactly one of -D AP or -D CLIENT"
#endif
#if (defined(EASY) + defined(HARD) + defined(FIVEEASY) + defined(FIVEHARD)) != 1
#error "Build with exactly one of -D EASY, -D HARD, -D FIVEEASY or -D FIVEHARD"
#endif

// FSSID is the network name. 802.11 allows 1-32 bytes and softAP refuses an
// empty one.
#ifndef FSSID
#error "FSSID must be defined in the conference header, a string of 1-32 characters"
#endif
static_assert(sizeof(FSSID) - 1 >= 1 && sizeof(FSSID) - 1 <= 32, "FSSID must be 1-32 characters");
// PSK is the WPA2 passphrase, 8-63 characters. softAP refuses 1-7 and an
// empty one would make an open network.
#ifndef PSK
#error "PSK must be defined in the conference header, a string of 8-63 characters"
#endif
static_assert(sizeof(PSK) - 1 >= 8 && sizeof(PSK) - 1 <= 63, "PSK must be 8-63 characters");

// MAC_ADDR is the Wi-Fi interface address, 6 bytes most significant first.
// Bit 0 of the first byte is the I/G bit; a device address has it clear and
// esp_wifi_set_mac refuses anything else.
#ifndef MAC_ADDR
#error "MAC_ADDR must be defined in the conference header, 6 bytes"
#endif
constexpr uint8_t rfhs_wifi_mac[] = MAC_ADDR;
static_assert(sizeof(rfhs_wifi_mac) == 6, "MAC_ADDR must be exactly 6 bytes");
static_assert((rfhs_wifi_mac[0] & 0x01) == 0, "MAC_ADDR: bit 0 of the first byte (I/G) must be 0, use an even first byte");
static_assert(!rfhs_all_bytes(rfhs_wifi_mac, 6, 0x00), "MAC_ADDR must not be all zeros");

// TXPOWER is one of the WIFI_POWER_* names. Only the values every supported
// core has are allowed; the newer core adds 20, 20.5 and 21 dBm names that
// the ESP32 and ESP32-S3 cores lack.
#ifndef TXPOWER
#error "TXPOWER must be defined in the conference header, a WIFI_POWER_* name from WIFI_POWER_19_5dBm down to WIFI_POWER_MINUS_1dBm"
#endif
static_assert(std::is_same<decltype(TXPOWER), wifi_power_t>::value, "TXPOWER must be a WIFI_POWER_* name, not a number");
static_assert(TXPOWER == WIFI_POWER_19_5dBm || TXPOWER == WIFI_POWER_19dBm || TXPOWER == WIFI_POWER_18_5dBm
           || TXPOWER == WIFI_POWER_17dBm || TXPOWER == WIFI_POWER_15dBm || TXPOWER == WIFI_POWER_13dBm
           || TXPOWER == WIFI_POWER_11dBm || TXPOWER == WIFI_POWER_8_5dBm || TXPOWER == WIFI_POWER_7dBm
           || TXPOWER == WIFI_POWER_5dBm || TXPOWER == WIFI_POWER_2dBm || TXPOWER == WIFI_POWER_MINUS_1dBm,
    "TXPOWER must be between WIFI_POWER_19_5dBm and WIFI_POWER_MINUS_1dBm");

#if !defined(TIME_TO_WAKE) || !defined(TIME_TO_SLEEP)
#error "TIME_TO_WAKE and TIME_TO_SLEEP must be defined in the conference header, in seconds"
#endif

#if defined(AP)
// CHANNEL: 0 picks a random channel every wake. The firmware sets country
// US, so a fixed 2.4 GHz channel is 1-11. A fixed 5 GHz channel is one of
// the US channels that need no radar detection: 36 40 44 48 149 153 157
// 161 165.
// TODO: support the DFS channels 52-144. They need radar detection the
// soft-AP does not do and did not work when tried.
// TODO: make the channel width settable. The AP uses the driver default
// (HT20 on 2.4 GHz, HT40 on 5 GHz); 40 MHz on 2.4 GHz and 80 MHz on 5 GHz
// would need the secondary channel chosen and checked against the band.
#ifndef CHANNEL
#error "CHANNEL must be defined in the conference header, 0 for random or a fixed channel"
#endif
#if defined(FIVEEASY) || defined(FIVEHARD)
#if !(CHANNEL == 0 || CHANNEL == 36 || CHANNEL == 40 || CHANNEL == 44 || CHANNEL == 48 \
   || CHANNEL == 149 || CHANNEL == 153 || CHANNEL == 157 || CHANNEL == 161 || CHANNEL == 165)
#error "5 GHz CHANNEL must be 0 (random) or one of 36 40 44 48 149 153 157 161 165"
#endif
#else
#if CHANNEL < 0 || CHANNEL > 11
#error "2.4 GHz CHANNEL must be 0 (random) or 1-11, the firmware sets country US"
#endif
#endif
// SSID_HIDDEN: 0 broadcasts the SSID in beacons, 1 hides it.
#ifndef SSID_HIDDEN
#error "SSID_HIDDEN must be defined in the conference header, 0 or 1"
#elif SSID_HIDDEN != 0 && SSID_HIDDEN != 1
#error "SSID_HIDDEN must be 0 or 1"
#endif
// MAX_CLIENTS: stations the soft-AP will accept. The radio has 17 hardware
// encryption keys and the core's sdkconfig reserves 7 for ESP-NOW on every
// supported chip, so 10 is the most any of them can take.
#ifndef MAX_CLIENTS
#error "MAX_CLIENTS must be defined in the conference header, 1-10"
#elif MAX_CLIENTS < 1 || MAX_CLIENTS > 10
#error "MAX_CLIENTS must be 1-10"
#endif
#endif

#if defined(CLIENT) && (defined(CHANNEL) || defined(SSID_HIDDEN) || defined(MAX_CLIENTS))
#error "CHANNEL, SSID_HIDDEN and MAX_CLIENTS only apply to AP mode, remove them from the CLIENT block"
#endif

void disableWiFi() {
 // fixes a noisy log error when monitoring
#if defined(AP)
  WiFi.softAPdisconnect(true);
#elif defined(CLIENT)
  WiFi.disconnect(true);
#endif
  WiFi.mode(WIFI_OFF);
  esp_wifi_stop();
  esp_wifi_deinit();
  esp_wifi_set_mode(WIFI_MODE_NULL);
}
