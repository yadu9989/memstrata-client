# AppImage

Build on the oldest supported Linux/glibc baseline:

```bash
./packaging/linux/appimage/build-appimage.sh \
  /secure-release/memstrata-eval-runtime \
  /secure-tools/appimagetool
```

The script never downloads a tool or runtime. Verify the AppImageKit release
and checksum separately, then supply its local path.

Test:

```bash
chmod +x packaging/linux/appimage/dist/*.AppImage
packaging/linux/appimage/dist/*.AppImage
```

AppImage has no publishing account or central official store. Publish the
immutable file, SHA-256, signature, SBOM, and provenance through the controlled
release page/CDN. Do not place the AppImage inside another archive.
