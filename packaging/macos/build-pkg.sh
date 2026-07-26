#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build-pkg.sh --runtime PATH [--version X.Y.Z] [--output-dir PATH]
                    [--application-identity NAME] [--installer-identity NAME]
                    [--notary-profile KEYCHAIN_PROFILE]

Builds a direct-distribution macOS PKG. Run only on macOS with a native runtime.
Signing and notarization are required for release.
EOF
}

runtime=""
version="0.1.0"
output_dir="$(cd "$(dirname "$0")" && pwd)/dist"
application_identity=""
installer_identity=""
notary_profile=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime) runtime="$2"; shift 2 ;;
    --version) version="$2"; shift 2 ;;
    --output-dir) output_dir="$2"; shift 2 ;;
    --application-identity) application_identity="$2"; shift 2 ;;
    --installer-identity) installer_identity="$2"; shift 2 ;;
    --notary-profile) notary_profile="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || {
  echo "This package must be built on macOS." >&2
  exit 1
}
[[ -n "$runtime" && -f "$runtime" ]] || {
  echo "--runtime must name a native macOS executable." >&2
  exit 1
}
[[ "$version" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || {
  echo "--version must be numeric dotted notation." >&2
  exit 1
}
[[ -n "$application_identity" && -n "$installer_identity" ]] || {
  echo "Release builds require both Developer ID signing identities." >&2
  exit 1
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
stage="$(mktemp -d "${TMPDIR:-/tmp}/memstrata-pkg.XXXXXX")"
trap 'case "$stage" in "${TMPDIR:-/tmp}"/memstrata-pkg.*) rm -rf -- "$stage" ;; esac' EXIT

install_root="$stage/root/usr/local/libexec/memstrata"
scripts_root="$stage/scripts"
mkdir -p "$install_root" "$scripts_root"
install -m 0755 "$runtime" "$install_root/memstrata-eval-runtime"

codesign --force --timestamp --options runtime \
  --entitlements "$script_dir/entitlements.plist" \
  --sign "$application_identity" \
  "$install_root/memstrata-eval-runtime"
codesign --verify --strict --verbose=2 "$install_root/memstrata-eval-runtime"

cat >"$scripts_root/postinstall" <<'EOF'
#!/bin/sh
set -eu
mkdir -p /usr/local/bin
ln -sfn /usr/local/libexec/memstrata/memstrata-eval-runtime \
  /usr/local/bin/memstrata-runtime
exit 0
EOF
chmod 0755 "$scripts_root/postinstall"

component="$stage/memstrata-runtime-component.pkg"
product="$output_dir/memstrata-client-${version}.pkg"

pkgbuild \
  --root "$stage/root" \
  --scripts "$scripts_root" \
  --identifier "com.calleditinc.memstrata.client.runtime" \
  --version "$version" \
  --install-location "/" \
  "$component"

productbuild \
  --package "$component" \
  --sign "$installer_identity" \
  "$product"

pkgutil --check-signature "$product"

if [[ -n "$notary_profile" ]]; then
  xcrun notarytool submit "$product" --keychain-profile "$notary_profile" --wait
  xcrun stapler staple "$product"
  xcrun stapler validate "$product"
else
  echo "PKG is signed but NOT notarized; pass --notary-profile before release." >&2
fi

shasum -a 256 "$product"
