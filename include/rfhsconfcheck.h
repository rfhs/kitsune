// Compile time helpers for checking conference header values. Everything
// here is constexpr or a macro so it can sit inside a static_assert and
// costs nothing on the device. Written for C++11, the oldest standard any
// core builds with.
#pragma once
#include <stdint.h>
#include <stddef.h>
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
