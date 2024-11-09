#!/bin/bash
set -e
set -u

if [ -z "${1:-}" ]; then
  printf "Please provide conference name\n"
fi
if [ -e "src/conferences/$(date +"%Y")${1}.h" ]; then
  printf "src/conferences/%s%s.h already exists, please remove it or pick a different name\n" "$(date +"%Y")" "${1}"
fi

get_mac() {
  printf '\{0xF2, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\}\n' $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256))
}

get_uuid() {
  uuidgen | tr '[:lower:]' '[:upper:]'
}

sed -e "s#{0x00, 0x01, 0x02, 0x03, 0x04, 0x05}#$(get_mac)#" \
  -e "s#{0x00, 0x06, 0x07, 0x08, 0x09, 0x0a}#$(get_mac)#" \
  -e "s#{0x00, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f}#$(get_mac)#" \
  -e "s#00000001-0002-0003-0004-000000000005#$(get_uuid)#" \
  -e "s#00000006-0007-0008-0009-00000000000a#$(get_uuid)#" \
  -e "s#0000000b-000c-000d-000e-00000000000f#$(get_uuid)#" \
  src/conferences/9999skel.h > "src/conferences/$(date +"%Y")${1}.h"
