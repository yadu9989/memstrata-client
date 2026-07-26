# Windows MSIX

Build on Windows with the Windows 10/11 SDK installed:

```powershell
.\packaging\windows\build-msix.ps1 `
  -RuntimeBinary C:\secure-release\memstrata-eval-runtime.exe `
  -Version 0.1.0.0
```

The manifest uses the reserved Store identity exactly:

- Name: `8351CalledItInc.memstrata-client`
- Publisher: `CN=BACE8B9E-8F65-4CF8-A7D4-808FE337B2B7`
- PFN: `8351CalledItInc.memstrata-client_xpfq096y27j6m`
- Store ID: `9MX65HPK0VX9`

The script deliberately emits `_unsigned.msix` unless a local test certificate
is supplied. The Microsoft Store signs accepted packages. Do not commit or
distribute an unsigned package.

The generated `M` logos are functional placeholders only. Replace every asset
with approved artwork and rerun Windows App Certification Kit before Store
submission.
