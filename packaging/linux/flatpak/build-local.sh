#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/native-linux/memstrata-eval-runtime" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$script_dir"
payload="$script_dir/payload"
build_root="$script_dir/build"
repo="$script_dir/repo"
manifest="$script_dir/io.github.yadu9989.MemStrataClient.local.json.in"
dist="$script_dir/dist"

rm -rf -- "$payload" "$build_root" "$repo"
mkdir -p "$payload" "$build_root" "$dist"
install -m 0755 "$runtime" "$payload/memstrata-eval-runtime"

flatpak-builder \
  --force-clean \
  --user \
  --install-deps-from=flathub \
  --repo="$repo" \
  "$build_root/app" \
  "$manifest"
flatpak build-bundle \
  "$repo" \
  "$dist/MemStrataClient-x86_64.flatpak" \
  io.github.yadu9989.MemStrataClient
sha256sum "$dist/MemStrataClient-x86_64.flatpak"
