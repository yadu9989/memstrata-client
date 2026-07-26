#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/native-linux/memstrata-eval-runtime" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
payload="$script_dir/payload"
dist="$script_dir/dist"

rm -rf -- "$payload"
mkdir -p "$payload" "$dist"
install -m 0755 "$runtime" "$payload/memstrata-eval-runtime"

(
  cd "$script_dir"
  snapcraft --output "$dist/memstrata-client_0.1.0_amd64.snap"
)

sha256sum "$dist/memstrata-client_0.1.0_amd64.snap"
echo "Local test only: sudo snap install --dangerous $dist/memstrata-client_0.1.0_amd64.snap"
