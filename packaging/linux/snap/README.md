# Snap

Build on Ubuntu:

```bash
sudo snap install snapcraft --classic
./packaging/linux/snap/build-snap.sh /secure-release/memstrata-eval-runtime
sudo snap install --dangerous packaging/linux/snap/dist/*.snap
memstrata-client.runtime
```

Before publishing:

1. Confirm the `memstrata-client` name is registered to the intended Snap Store
   account.
2. Change `grade` from `devel` to `stable` in a reviewed release commit.
3. Run protocol, activation, refresh, upgrade, and remove/reinstall tests on a
   clean supported Ubuntu host.
4. `snapcraft upload --release=edge <package.snap>`.
5. Promote from `edge` only after Store review and design-partner validation.

The package requests no interfaces because the prototype is offline and uses
stdin/stdout plus snap-owned state. Add `network` only when a reviewed lease
client actually requires it.
