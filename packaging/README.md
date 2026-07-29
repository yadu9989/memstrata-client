# Open runtime packaging harness

These templates package a separately supplied MemStrata runtime. They contain
no runtime executable, license key, signing credential, private source,
download URL, or proprietary algorithm.

The operator must supply a native runtime binary:

```text
Windows binary -> packaging/windows/build-msix.ps1
macOS binary   -> packaging/macos/build-pkg.sh
Linux binary   -> packaging/linux/{snap,appimage,flatpak}/
```

Each script stages inputs in an ignored build directory and emits packages in
an ignored dist directory. Generated packages must not be committed.

Static contract check:

```bash
python packaging/validate.py
```

The private release process must pin the public packager commit and verify the
runtime SHA-256 before invoking these scripts.
