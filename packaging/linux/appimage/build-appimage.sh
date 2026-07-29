#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 || ! -f "$1" || ! -f "$2" || ! -f "$3" ]]; then
  echo "Usage: $0 RUNTIME APPIMAGETOOL TYPE2_RUNTIME" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
appimagetool="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
type2_runtime="$(cd "$(dirname "$3")" && pwd)/$(basename "$3")"

appdir="$script_dir/build/MemStrataClient.AppDir"
dist="$script_dir/dist"
rm -rf -- "$appdir"
mkdir -p \
  "$appdir/usr/bin" \
  "$appdir/usr/share/applications" \
  "$appdir/usr/share/icons/hicolor/scalable/apps" \
  "$appdir/usr/share/metainfo" \
  "$dist"

install -m 0755 "$runtime" "$appdir/usr/bin/memstrata-eval-runtime"
install -m 0755 "$script_dir/AppRun" "$appdir/AppRun"
install -m 0644 "$script_dir/memstrata-client.desktop" "$appdir/memstrata-client.desktop"
install -m 0644 "$script_dir/memstrata-client.desktop" \
  "$appdir/usr/share/applications/memstrata-client.desktop"
install -m 0644 "$script_dir/memstrata-client.svg" "$appdir/memstrata-client.svg"
install -m 0644 "$script_dir/memstrata-client.svg" \
  "$appdir/usr/share/icons/hicolor/scalable/apps/memstrata-client.svg"
install -m 0644 "$script_dir/memstrata-client.appdata.xml" \
  "$appdir/usr/share/metainfo/memstrata-client.appdata.xml"

ARCH=x86_64 "$appimagetool" \
  --no-appstream \
  --runtime-file "$type2_runtime" \
  "$appdir" \
  "$dist/MemStrata_Client-x86_64.AppImage"
sha256sum "$dist/MemStrata_Client-x86_64.AppImage"
