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
if [ -f "$(date +"%Y")${1}.txt" ]; then
  printf '%s%s.txt already exists, please remove it or pick a different name\n' "$(date +"%Y")" "${1}"
  exit 1
fi

# Safety checks complete, define functions and do the thing
threewords() {
  if [ ! -r '/usr/share/dict/cracklib-words' ]; then
    printf 'Unable to find /usr/share/dict/cracklib-words\n'
    exit 1
  fi
  dictionary='/usr/share/dict/cracklib-words'
  shuf -n3 "${dictionary}" | tr '[:lower:]' '[:upper:]' | paste -sd ' ' | dos2unix
}
export -f threewords

for challenge in bluetooth/iBeacon bluetooth/classic_discoverable wifi/wifi_ap_client; do
  pushd "${challenge}" > /dev/null 2>&1
  printf "Rolling %s for %s%s... " "${challenge}" "$(date +"%Y")" "${1}"
  ./make_conference.sh "${1}"
  if [ ! -e "src/conferences/$(date +"%Y")${1}.h" ]; then
    printf "Something went wrong creating %s/src/conferences/%s%s.h, please scroll up\n" "${challenge}" "$(date +"%Y")" "${1}"
    exit 1
  fi
  ln -snf "conferences/$(date +"%Y")${1}.h" src/current_conf.h
  grep -e 'RFHS_CHALLENGE_NAME\|FOX_KEYWORDS\|NAME\|UUID\|MAC_ADDR\|FSSID\|CHANNEL' "src/conferences/$(date +"%Y")${1}.h" | sed -e 's#{##' -e 's#}##' -e 's#0x##g' -e 's#, #:#g' | tee -a "${OLDPWD}/$(date +"%Y")${1}.txt" > /dev/null 2>&1
  printf "complete\n"
  popd > /dev/null 2>&1
done
printf "Formatting with conference name for %s%s... " "$(date +"%Y")" "${1}"
sed -i \
  -e "/RFHS_CHALLENGE_NAME/{h; s/.*/printf -- '-\\n----------------------------------------------------------------\\nConference: %s%s\\n\\n' \"\$(date +%Y)\" \"${1}\"/e; G;}" \
  "$(date +"%Y")${1}.txt"
printf "complete\n"

printf "Adding instructions..."
sed -i -e "/FOX_KEYWORDS/{h; s/.*/printf -- '\n%s\n\n' \"\$(cat foxhunt_instructions.txt)\"/e; G;}" \
  "$(date +"%Y")${1}.txt"
printf "complete\n"

printf "Seeding keys for %s%s... " "$(date +"%Y")" "${1}"
#this works despite shell check thinking it does not
#shellcheck disable=2016
sed -i -e 's/\(.*\)[F]OXFLAG\(.*\)/printf "%s%s%s\\n" \x22\1\x22 "\$(threewords)" \x22\2\x22/e' "$(date +"%Y")${1}.txt"
printf "complete\n"

sed -i '1iSet font to "Roboto Mono"' "$(date +"%Y")${1}.txt"

printf "Generation Complete\n"
