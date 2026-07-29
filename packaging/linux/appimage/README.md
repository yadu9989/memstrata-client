# AppImage

Build on the oldest supported Linux/glibc baseline:

```bash
./packaging/linux/appimage/build-appimage.sh \
  /secure-release/memstrata-eval-runtime \
  /secure-tools/appimagetool \
  /secure-tools/runtime-x86_64
```

The script never downloads a tool or runtime. Verify both the AppImageKit
`appimagetool` release and the matching AppImage Type-2 runtime release and
checksums separately, then supply their local paths. Requiring
`--runtime-file` prevents `appimagetool` from silently downloading a mutable
`continuous` runtime during packaging.

The build disables `appimagetool`'s implicit AppStream subprocess and ships a
reviewable AppStream document in the AppDir. Validate that document separately
with the pinned release container/toolchain; do not let an unpinned host
validator become part of package generation.

Test:

```bash
chmod +x packaging/linux/appimage/dist/*.AppImage
packaging/linux/appimage/dist/*.AppImage
```

AppImage has no publishing account or central official store. Publish the
immutable file, SHA-256, signature, SBOM, and provenance through the controlled
release page/CDN. Do not place the AppImage inside another archive.
