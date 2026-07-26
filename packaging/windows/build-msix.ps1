[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeBinary,

    [ValidatePattern("^\d+\.\d+\.\d+\.\d+$")]
    [string]$Version = "0.1.0.0",

    [string]$OutputDirectory = (Join-Path $PSScriptRoot "dist"),

    [string]$MakeAppxPath = ""
)

$ErrorActionPreference = "Stop"
$runtime = (Resolve-Path -LiteralPath $RuntimeBinary).Path
if ([System.IO.Path]::GetExtension($runtime) -ne ".exe") {
    throw "RuntimeBinary must be a native Windows .exe."
}

if (-not $MakeAppxPath) {
    $sdkBin = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    $candidate = Get-ChildItem -LiteralPath $sdkBin -Directory -ErrorAction Stop |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "x64\makeappx.exe" } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $candidate) {
        throw "MakeAppx.exe was not found. Install the Windows SDK or pass -MakeAppxPath."
    }
    $MakeAppxPath = $candidate
}
$MakeAppxPath = (Resolve-Path -LiteralPath $MakeAppxPath).Path

$output = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($output) | Out-Null
$stage = Join-Path ([System.IO.Path]::GetTempPath()) (
    "memstrata-msix-" + [System.Guid]::NewGuid().ToString("N")
)
[System.IO.Directory]::CreateDirectory($stage) | Out-Null

try {
    $runtimeDir = Join-Path $stage "runtime"
    $assetDir = Join-Path $stage "Assets"
    [System.IO.Directory]::CreateDirectory($runtimeDir) | Out-Null
    Copy-Item -LiteralPath $runtime -Destination (
        Join-Path $runtimeDir "memstrata-eval-runtime.exe"
    )

    & (Join-Path $PSScriptRoot "generate-placeholder-assets.ps1") -OutputDirectory $assetDir

    $template = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "AppxManifest.xml.in")
    $manifest = $template.Replace("@VERSION@", $Version)
    Set-Content -LiteralPath (Join-Path $stage "AppxManifest.xml") -Value $manifest -Encoding utf8

    $package = Join-Path $output "memstrata-client_$($Version)_x64_unsigned.msix"
    & $MakeAppxPath pack /o /d $stage /p $package
    if ($LASTEXITCODE -ne 0) {
        throw "MakeAppx failed with exit code $LASTEXITCODE."
    }

    Write-Warning "Output is unsigned and cannot be installed. Store submission applies its signature."

    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $package).Hash.ToLowerInvariant()
    Write-Output "Package: $package"
    Write-Output "SHA-256: $digest"
}
finally {
    if (Test-Path -LiteralPath $stage) {
        $resolvedStage = (Resolve-Path -LiteralPath $stage).Path
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if (-not $resolvedStage.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected staging path: $resolvedStage"
        }
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
