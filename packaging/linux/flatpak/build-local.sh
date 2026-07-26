#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/native-linux/memstrata-eval-runtime" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
payload="$script_dir/payload"
builddir="$script_dir/build"
repo="$script_dir/repo"
manifest="$script_dir/build/io.github.yadu9989.MemStrataClient.local.json"
dist="$script_dir/dist"

rm -rf -- "$payload" "$builddir" "$repo"
mkdir -p "$payload" "$builddir" "$dist"
install -m 0755 "$runtime" "$payload/memstrata-eval-runtime"
cp "$script_dir/io.github.yadu9989.MemStrataClient.local.json.in" "$manifest"

flatpak-builder \
  --force-clean \
  --install-deps-from=flathub \
  --repo="$repo" \
  "$builddir/app" \
  "$manifest"
flatpak build-bundle \
  "$repo" \
  "$dist/MemStrataClient-x86_64.flatpak" \
  io.github.yadu9989.MemStrataClient
sha256sum "$dist/MemStrataClient-x86_64.flatpak"
