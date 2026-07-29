# macOS direct distribution

This produces a signed/notarized command-line `.pkg` for distribution outside
the Mac App Store. It does not claim Mac App Store compatibility.

Prerequisites:

- native macOS runtime built and tested on each target architecture;
- Apple Developer Program membership;
- `Developer ID Application` and `Developer ID Installer` certificates in the
  signing keychain;
- Xcode command line tools;
- a Keychain notary profile or App Store Connect API key.

Store the notary credential interactively (the Apple ID email identifies the
account but is not itself a credential):

```bash
xcrun notarytool store-credentials "memstrata-notary" \
  --apple-id "<APPLE-DEVELOPER-EMAIL>" \
  --team-id "<TEAM-ID>"
```

Build:

```bash
./packaging/macos/build-pkg.sh \
  --runtime /secure-release/memstrata-eval-runtime \
  --version 0.1.0 \
  --application-identity "Developer ID Application: Called It Inc (<TEAM-ID>)" \
  --installer-identity "Developer ID Installer: Called It Inc (<TEAM-ID>)" \
  --notary-profile memstrata-notary
```

Verify on a clean supported Mac:

```bash
pkgutil --check-signature packaging/macos/dist/memstrata-client-0.1.0.pkg
spctl --assess --type install --verbose=4 packaging/macos/dist/memstrata-client-0.1.0.pkg
sudo installer -pkg packaging/macos/dist/memstrata-client-0.1.0.pkg -target /
memstrata-runtime
```

The empty entitlement set is intentional: add only a capability proven
necessary. Hardened runtime is enabled by `codesign --options runtime`.

For the Mac App Store, first design a sandboxed `.app` host, obtain the App
Store distribution profile/certificates, and validate store policy. A
Developer-ID PKG cannot be uploaded as a Mac App Store app.
