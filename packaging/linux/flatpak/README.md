# Flatpak / Flathub

Local build:

```bash
flatpak remote-add --if-not-exists --user flathub \
  https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub \
  org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08
./packaging/linux/flatpak/build-local.sh /secure-release/memstrata-eval-runtime
flatpak install --user packaging/linux/flatpak/dist/*.flatpak
flatpak run io.github.yadu9989.MemStrataClient
```

The Flathub template uses `extra-data` so the proprietary runtime is fetched
from an immutable vendor URL at install time without entering this repository.
Before submission, replace all placeholders with the exact HTTPS URL, SHA-256,
and byte size of a signed native Linux runtime.

The proposed ID is `io.github.yadu9989.MemStrataClient`. Flathub must approve
the ID/ownership and the extra-data licensing model. Do not claim Flathub
availability until its review passes.
