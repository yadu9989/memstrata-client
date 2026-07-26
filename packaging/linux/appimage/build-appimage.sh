#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/native-linux/memstrata-eval-runtime [appimagetool]" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
appimagetool="${2:-appimagetool}"
command -v "$appimagetool" >/dev/null 2>&1 || {
  echo "appimagetool not found; supply a verified AppImageKit binary path." >&2
  exit 1
}

appdir="$script_dir/build/MemStrataClient.AppDir"
dist="$script_dir/dist"
rm -rf -- "$appdir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/scalable/apps" "$dist"

install -m 0755 "$runtime" "$appdir/usr/bin/memstrata-eval-runtime"
install -m 0755 "$script_dir/AppRun" "$appdir/AppRun"
install -m 0644 "$script_dir/memstrata-client.desktop" "$appdir/memstrata-client.desktop"
install -m 0644 "$script_dir/memstrata-client.desktop" \
  "$appdir/usr/share/applications/memstrata-client.desktop"
install -m 0644 "$script_dir/memstrata-client.svg" "$appdir/memstrata-client.svg"
install -m 0644 "$script_dir/memstrata-client.svg" \
  "$appdir/usr/share/icons/hicolor/scalable/apps/memstrata-client.svg"

ARCH=x86_64 "$appimagetool" "$appdir" "$dist/MemStrata_Client-x86_64.AppImage"
sha256sum "$dist/MemStrata_Client-x86_64.AppImage"
