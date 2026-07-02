#!/bin/bash
set -e
set -u

# Ensure we have a conference name
if [ -z "${1:-}" ]; then
  printf "Please provide conference name\n"
  exit 1
fi

# Check if that conference name already exists
for challenge in bluetooth/iBeacon bluetooth/classic_discoverable wifi/wifi_ap_client; do
  pushd "${challenge}" > /dev/null 2>&1
  if [ -e "src/conferences/$(date +"%Y")${1}.h" ]; then
    printf "%s/src/conferences/%s%s.h already exists, please remove it or pick a different name\n" "${challenge}" "$(date +"%Y")" "${1}"
    exit 1
  fi
  popd > /dev/null 2>&1
done

# Safety checks complete, define functions and do the thing
threewords() {
  dictionary='/usr/share/dict/cracklib-words'
  shuf -n3 "${dictionary}" | paste -sd ' '
}

for challenge in bluetooth/iBeacon bluetooth/classic_discoverable wifi/wifi_ap_client; do
  pushd "${challenge}" > /dev/null 2>&1
  printf "Rolling %s for %s%s... " "${challenge}" "$(date +"%Y")" "${1}"
  ./make_conference.sh "${1}"
  if [ ! -e "src/conferences/$(date +"%Y")${1}.h" ]; then
    printf "Something went wrong creating %s/src/conferences/%s%s.h, please scroll up\n" "${challenge}" "$(date +"%Y")" "${1}"
    exit 1
  fi
  ln -snf "src/conferences/$(date +"%Y")${1}.h" src/current_conf.h
  grep -e 'RFHS_CHALLENGE_NAME\|NAME\|UUID\|MAC_ADDR\|FSSID\|CHANNEL' "src/conferences/$(date +"%Y")${1}.h" | sed -e 's#{##' -e 's#}##' -e 's#0x##g' -e 's#, #:#g' | tee -a "${OLDPWD}/$(date +"%Y")${1}.txt" > /dev/null 2>&1
  printf "complete\n"
  popd > /dev/null 2>&1
done
printf "Seeding keys for %s%s... " "$(date +"%Y")" "${1}"
sed -i \
  -e "/RFHS_CHALLENGE_NAME/i -\n----------------------------------------------------------------\n$(date +"%Y")${1}\n$(threewords)\n" \
  "$(date +"%Y")${1}.txt"
printf "complete\n"
