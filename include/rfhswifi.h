#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_system.h>
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
RFHS_CHECK_ADDRESS(rfhs_wifi_mac, 6);

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

// The awake LED colour: green for an access point, orange for a client.
#if defined(AP)
#define RFHS_AWAKE_COLOR 0x00FF00
#else
#define RFHS_AWAKE_COLOR 0xFF8C00
#endif
constexpr uint32_t rfhs_awake_color = RFHS_AWAKE_COLOR;

#if defined(AP)
// The channel the access point was started on, for the readback.
static int set_channel;
#endif

// Starts the driver, sets the address, applies the country, picks the
// channel and starts the access point or the client, then applies TXPOWER.
// WiFi.mode() starts the driver before the address is set and
// esp_wifi_init() runs once more after it.
bool rfhsstartradio() {
  wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
#if defined(AP)
  WiFi.mode(WIFI_AP);
  wifi_interface_t interface = WIFI_IF_AP;
#elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  wifi_interface_t interface = WIFI_IF_STA;
#endif
  esp_wifi_init(&cfg);

  uint8_t mac_addr[6] = MAC_ADDR;
  if (!rfhsmacset(esp_wifi_set_mac(interface, mac_addr) == ESP_OK)) {
    return false;
  }

  // Keeping the configuration in RAM has to come after the address set;
  // before it, the address set fails on the ESP32-C5.
  esp_wifi_set_storage(WIFI_STORAGE_RAM);

  // The regulatory domain is set before the network starts, as the two
  // letter ISO code; the true has the driver enforce the country's rules.
  esp_err_t err = esp_wifi_set_country_code("US", true);
  if (err != ESP_OK) {
    Serial.printf("Error setting country code: %s\r\n", esp_err_to_name(err));
    return false;
  }

#if defined(AP)
#if CHANNEL > 0
  set_channel = CHANNEL;
#else
#if defined(FIVEEASY) || defined(FIVEHARD)
  // The US 5 GHz channels that need no radar detection.
  static constexpr uint8_t CHANNEL_LIST_5G[] = {
    36, 40, 44, 48, 149, 153, 157, 161, 165
  };
  constexpr size_t total_elements = sizeof(CHANNEL_LIST_5G) / sizeof(CHANNEL_LIST_5G[0]);
  size_t random_index = esp_random() % total_elements;
  set_channel = CHANNEL_LIST_5G[random_index];
#else
  // Only the 2.4 GHz channels every country allows, 1-11.
  set_channel = esp_random() % 11;
  set_channel++;
#endif
#endif
  // The channel goes out before the radio starts, so a sniffer that reads
  // it over serial can be on the channel for the first beacon. The flush
  // moves the line out of the UART or the USB FIFO before the start. On a
  // native USB board the host may not have the port open this early, so the
  // Operating channel readback after the start remains the record.
  Serial.printf("Starting on channel %d\r\n", set_channel);
  Serial.flush();
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(FSSID, PSK, set_channel, SSID_HIDDEN, MAX_CLIENTS)) {
    return false;
  }
  // The access point needs a moment before anything reads it back.
  delay(100);
#elif defined(CLIENT)
  WiFi.mode(WIFI_STA);
  if (WiFi.begin(FSSID, PSK) == WL_CONNECT_FAILED) {
    return false;
  }
  // The client needs a moment before anything reads it back.
  delay(100);
#endif
  bool power_set = WiFi.setTxPower(TXPOWER);
  Serial.printf("Set power status: %s\r\n", power_set ? "ok" : "failed");
  return power_set;
}

// Prints the configuration the stack is running with and refuses to run
// when it differs from the conference header. The address comes from
// esp_wifi_get_mac() and the channel from the driver; the SSID, the PSK and,
// for the AP, the hidden flag and the client limit come from
// esp_wifi_get_config(). The SSID field is 32 bytes without a terminator
// when the name is 32 characters long, so it is copied out before it is
// printed. TXPOWER is printed as configured: WiFi.getTxPower() returns the
// PHY's own maximum, which the driver documents as a step below several of
// the WIFI_POWER_* values (68 reads back as 66, 78 as 72), so a readback
// compared with the name would halt a working fox. A refused set is caught
// in rfhsstartradio() instead.
bool rfhscheckradio() {
  wifi_config_t conf;
  uint8_t mac[6];
#if defined(AP)
  esp_wifi_get_mac(WIFI_IF_AP, mac);
  esp_err_t err = esp_wifi_get_config(WIFI_IF_AP, &conf);
  const uint8_t *ssid_field = conf.ap.ssid;
  const char *psk = (const char *)conf.ap.password;
#elif defined(CLIENT)
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  esp_err_t err = esp_wifi_get_config(WIFI_IF_STA, &conf);
  const uint8_t *ssid_field = conf.sta.ssid;
  const char *psk = (const char *)conf.sta.password;
#endif
  if (!rfhscheckaddress(mac, rfhs_wifi_mac, sizeof(rfhs_wifi_mac), false)) {
    return false;
  }
  if (err != ESP_OK) {
    Serial.printf("Error reading the Wi-Fi configuration: %s\r\n", esp_err_to_name(err));
    return false;
  }
  char ssid[sizeof(conf.ap.ssid) + 1];
  memcpy(ssid, ssid_field, sizeof(conf.ap.ssid));
  ssid[sizeof(conf.ap.ssid)] = '\0';
#if defined(AP)
  if (!rfhscheckint("Operating channel", "channel", WiFi.channel(), set_channel, "")) {
    return false;
  }
#endif
  if (!rfhscheckstr("Operating SSID", "SSID", ssid, FSSID, false)) {
    return false;
  }
  if (!rfhscheckstr("Operating PSK", "PSK", psk, PSK, false)) {
    return false;
  }
#if defined(AP)
  if (!rfhscheckint("Hidden SSID", "hidden SSID", conf.ap.ssid_hidden, SSID_HIDDEN, "")) {
    return false;
  }
  if (!rfhscheckint("Max clients", "max clients", conf.ap.max_connection, MAX_CLIENTS, "")) {
    return false;
  }
#endif
  Serial.println("Tx power: " RFHS_STR(TXPOWER));
  return true;
}

// Takes the network down and the driver with it, which also silences a log
// error the driver prints otherwise.
void rfhsstopradio() {
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
