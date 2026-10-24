#!/usr/bin/env bash
set -euo pipefail
image="${1:-skabrits/fusion360:3.3.0}"
docker run --rm --entrypoint bash "$image" -lc '
set -eu
launcher=/etc/s6-overlay/s6-rc.d/svc-xorg/run
test -s "$launcher"
help="$(/usr/bin/Xvfb -help 2>&1 || true)"
for flag in -vfbdevice -glamor; do
  if grep -q -- "$flag" "$launcher"; then
    if ! printf "%s\n" "$help" | grep -q -- "$flag"; then
      printf "FAIL: launcher needs %s but Xvfb help omits it\n" "$flag" >&2
      exit 1
    fi
  fi
done
echo "PASS: Xvfb capabilities match Webtop launcher"
'
