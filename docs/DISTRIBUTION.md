# MemStrata distribution

This document distinguishes the open client from the commercial runtime. It is
release guidance, not proof that any package has been signed, notarized,
reviewed, or published.

## Two artifacts, one protocol

| Artifact | License | Channel | Contains |
| --- | --- | --- | --- |
| `memstrata-client` | Apache-2.0 | PyPI | API, CLI, transport, strict validation, mock |
| MemStrata evaluation runtime | Commercial evaluation terms | OS stores/direct download | Signed entitlement enforcement and private engine |

The public repository never contains a runtime executable. Every OS packager
requires an explicit local `--runtime`/`-RuntimeBinary` path and refuses to
build without it. A release operator must verify the runtime digest against the
private release manifest before packaging.

## PyPI: Trusted Publishing

Production publisher tuple:

- PyPI project: `memstrata-client`
- GitHub owner: `yadu9989`
- GitHub repository: `memstrata-client`
- Workflow: `release.yml`
- GitHub environment: `pypi`

Test publisher tuple:

- TestPyPI project: `memstrata-client`
- GitHub owner: `yadu9989`
- GitHub repository: `memstrata-client`
- Workflow: `test-release.yml`
- GitHub environment: `testpypi`

Configure both as Trusted Publishers in the corresponding PyPI accounts. The
project can be registered as a pending publisher before its first release. Do
not create or store a long-lived PyPI API token.

Release order:

1. Protect both GitHub environments with required manual approval.
2. Run the `Test release` workflow manually and install its exact version from
   TestPyPI in a clean environment.
3. Confirm the wheel boundary scan, `twine check`, CLI smoke, and provenance.
4. Create an annotated `vX.Y.Z` tag from a reviewed commit.
5. Approve the production `pypi` environment only after the build job passes.

The workflows refuse versions that do not match the tag/input and build from a
clean checkout. A PyPI project is not considered created until the first
Trusted Publishing upload succeeds.

## Runtime package release gate

No runtime package is publishable until all of these are recorded:

- native binary built on the target operating system and architecture;
- private release-manifest SHA-256 match;
- package generated from a reviewed packager commit;
- platform signature verified;
- SBOM and provenance attached;
- malware/reputation scan complete;
- clean-machine install, license activation, protocol smoke, upgrade, and
  uninstall tests pass;
- evaluation EULA and privacy notice approved by qualified counsel;
- store metadata, support URL, privacy URL, and deletion-request path live.

## Platform truth table

| Platform | Prepared output | What still makes it publishable |
| --- | --- | --- |
| Windows | unsigned x64 `.msix` | Store ingestion/signing, WACK, clean VM test |
| macOS | `.pkg` script and entitlements | native macOS binary, Developer ID certificates, notarization and stapling |
| Snap | strict-confinement manifest | native Linux binary, name registration, review, clean-host test |
| AppImage | AppDir/AppImage script | native Linux binary, appimagetool verification, signature and hosted immutable release |
| Flatpak | local and extra-data manifests | native Linux binary, final URL/hash/size, Flathub app-ID ownership and review |

## Microsoft Store

The private product configuration carries Store ID `9MX65HPK0VX9` and the
reserved package identity. The package manifest is a desktop/full-trust command
line companion, not a GUI. Build an x64 MSIX with
`packaging/windows/build-msix.ps1`; inspect it with `makeappx unpack`; then run
Windows App Certification Kit on a clean Windows 11 VM.

In Partner Center, create a submission for the reserved product, upload the
MSIX (or a manually assembled `.msixupload`), complete age ratings, properties,
privacy/support URLs, and at least one localized listing, then submit to a
private audience before public availability. Microsoft Store applies the
production signature after certification. Do not sideload the unsigned build.

## Apple distribution

`packaging/macos/build-pkg.sh` prepares direct distribution outside the Mac App
Store:

1. compile the runtime natively on macOS;
2. sign the executable with `Developer ID Application` and hardened runtime;
3. build/sign the installer with `Developer ID Installer`;
4. submit with `xcrun notarytool`, wait for acceptance, staple, and validate.

The Apple account email is an operator login, not a signing identity. Never put
the Apple ID password or an app-specific password in a command, script, or Git
secret. Store a notary profile in Keychain with `notarytool
store-credentials`, or use an App Store Connect API key from CI.

A Mac App Store build is intentionally not claimed here. It requires a
sandboxed `.app`, App Store distribution certificates/profiles, receipts, and
review of whether spawning a protocol runtime is compatible with store policy.

## Linux publishing

- Snap: register the name, run `snapcraft`, install with `--dangerous` only for
  local unsigned tests, then upload first to `edge`.
- AppImage: build the AppDir on the oldest supported glibc baseline, run
  `appimagetool`, sign the immutable release, and publish it with SHA-256/SBOM.
  AppImage has no central account or official store login.
- Flatpak: validate locally with `flatpak-builder`, test the generated bundle,
  then submit the manifest to Flathub. The proposed app ID is
  `io.github.yadu9989.MemStrataClient`; Flathub must validate ownership and the
  proprietary extra-data terms.

Account emails are deliberately absent from manifests and logs.
