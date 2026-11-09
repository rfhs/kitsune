// Helpers for checking conference header values. The compile time part is
// constexpr functions and macros that sit inside a static_assert and cost
// nothing on the device; the runtime part prints a value read back from the
// stack and compares it with the header. Written for C++11, the oldest
// standard any core builds with.
#pragma once
#include <Arduino.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
// The text of a macro's value as a string literal, so a header can compare
// or print the way a value was written rather than the number it expands to.
#define RFHS_STR_(x) #x
#define RFHS_STR(x) RFHS_STR_(x)

// The two strings are equal, so a header can compare the text RFHS_STR
// gives it, for example a bare 0 against 0x0000.
constexpr bool rfhs_str_eq(const char *a, const char *b) {
  return *a == *b && (*a == '\0' || rfhs_str_eq(a + 1, b + 1));
}

// Every byte of the array equals value. Catches an all zero or all 0xFF
// address, which no radio accepts as a device address.
constexpr bool rfhs_all_bytes(const uint8_t *a, size_t n, uint8_t value) {
  return n == 0 ? true : (a[0] == value && rfhs_all_bytes(a + 1, n - 1, value));
}

// The checks every MAC_ADDR gets: name is the constexpr array a header made
// from the conference value and N its length in bytes. Bit 0 of the first
// byte is the I/G bit and a device address has it clear; all zeros is not an
// address on any radio.
#define RFHS_CHECK_ADDRESS(name, N) \
  static_assert(sizeof(name) == (N), "MAC_ADDR must be exactly " #N " bytes"); \
  static_assert((name[0] & 0x01) == 0, "MAC_ADDR: bit 0 of the first byte (I/G) must be 0, use an even first byte"); \
  static_assert(!rfhs_all_bytes(name, N, 0x00), "MAC_ADDR must not be all zeros")

constexpr bool rfhs_is_hex(char c) {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

// A 36 character UUID string: 8-4-4-4-12 hex digits with hyphens between
// the groups and nothing after. The BLE library accepts only this form and
// silently leaves the UUID unset for anything else.
constexpr bool rfhs_uuid_ok(const char *s, size_t i = 0) {
  return i == 36 ? s[i] == '\0'
       : (i == 8 || i == 13 || i == 18 || i == 23) ? (s[i] == '-' && rfhs_uuid_ok(s, i + 1))
       : (rfhs_is_hex(s[i]) && rfhs_uuid_ok(s, i + 1));
}

// Readback helpers. Each prints "<label>: <value>", compares the value with
// the one the conference header asked for and, when they differ, prints
// "Requested <thing>: <value>" and "<label> != Requested <thing>" and
// returns false. label is the readback line's label, thing the short name
// the two mismatch lines use. The format of every value is fixed by the
// helper, so -Wformat checks each print.

// n bytes, printed two hex digits each with colons between, most
// significant first. With reversed set, bytes is stored least significant
// byte first, the way the Zigbee stack keeps addresses, and is printed from
// its last byte.
static void rfhsprintbytes(const uint8_t *bytes, size_t n, bool reversed) {
  for (size_t i = 0; i < n; i++) {
    uint8_t byte = bytes[reversed ? n - 1 - i : i];
    if (i > 0) {
      Serial.print(':');
    }
    Serial.printf("%02X", byte);
  }
}

// An address or another byte string. want is most significant byte first,
// as every conference header writes it; got follows reversed.
bool rfhscheckbytes(const char *label, const char *thing, const uint8_t *got, const uint8_t *want,
                    size_t n, bool reversed) {
  Serial.printf("%s: ", label);
  rfhsprintbytes(got, n, reversed);
  Serial.println();
  for (size_t i = 0; i < n; i++) {
    if (got[reversed ? n - 1 - i : i] != want[i]) {
      Serial.printf("Requested %s: ", thing);
      rfhsprintbytes(want, n, false);
      Serial.println();
      Serial.printf("%s != Requested %s\r\n", label, thing);
      return false;
    }
  }
  return true;
}

// The device address, the first readback line of every fox.
bool rfhscheckaddress(const uint8_t *got, const uint8_t *want, size_t n, bool reversed) {
  return rfhscheckbytes("Device address", "address", got, want, n, reversed);
}

// A decimal value; unit is appended to the value, "s" or " dBm" or "".
bool rfhscheckint(const char *label, const char *thing, int got, int want, const char *unit) {
  Serial.printf("%s: %d%s\r\n", label, got, unit);
  if (got != want) {
    Serial.printf("Requested %s: %d%s\r\n", thing, want, unit);
    Serial.printf("%s != Requested %s\r\n", label, thing);
    return false;
  }
  return true;
}

// A 16 bit identifier, printed 0x%04X like Kismet shows it, with the decimal
// value in parentheses after it when with_decimal is set.
bool rfhscheckhex16(const char *label, const char *thing, unsigned got, unsigned want, bool with_decimal) {
  if (with_decimal) {
    Serial.printf("%s: 0x%04X (%u)\r\n", label, got, got);
  } else {
    Serial.printf("%s: 0x%04X\r\n", label, got);
  }
  if (got != want) {
    if (with_decimal) {
      Serial.printf("Requested %s: 0x%04X (%u)\r\n", thing, want, want);
    } else {
      Serial.printf("Requested %s: 0x%04X\r\n", thing, want);
    }
    Serial.printf("%s != Requested %s\r\n", label, thing);
    return false;
  }
  return true;
}

// A string. ignorecase compares hex digits written in either case, which a
// UUID allows.
bool rfhscheckstr(const char *label, const char *thing, const char *got, const char *want, bool ignorecase) {
  Serial.printf("%s: %s\r\n", label, got);
  if ((ignorecase ? strcasecmp(got, want) : strcmp(got, want)) != 0) {
    Serial.printf("Requested %s: %s\r\n", thing, want);
    Serial.printf("%s != Requested %s\r\n", label, thing);
    return false;
  }
  return true;
}
