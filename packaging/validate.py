"""Static validation for the public packaging harness."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRODUCT = json.loads((ROOT / "product.json").read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    windows = PRODUCT["windows"]
    require(
        windows["identity_name"] == "8351CalledItInc.memstrata-client",
        "unexpected Windows identity",
    )
    require(
        windows["publisher"] == "CN=BACE8B9E-8F65-4CF8-A7D4-808FE337B2B7",
        "unexpected Windows publisher",
    )
    expected_pfn = f'{windows["identity_name"]}_xpfq096y27j6m'
    require(windows["package_family_name"] == expected_pfn, "unexpected PFN")
    require(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", "0.1.0.0") is not None, "bad version")

    manifest = (ROOT / "windows" / "AppxManifest.xml.in").read_text(encoding="utf-8")
    parsed = ET.fromstring(manifest.replace("@VERSION@", "0.1.0.0"))
    identity = parsed.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Identity")
    require(identity is not None, "Windows Identity missing")
    require(identity.attrib["Name"] == windows["identity_name"], "manifest identity mismatch")
    require(identity.attrib["Publisher"] == windows["publisher"], "manifest publisher mismatch")

    snap = (ROOT / "linux" / "snap" / "snapcraft.yaml").read_text(encoding="utf-8")
    require("source: payload" in snap, "snap must use operator-staged payload")
    require("confinement: strict" in snap, "snap must remain strictly confined")

    appimage_script = (
        ROOT / "linux" / "appimage" / "build-appimage.sh"
    ).read_text(encoding="utf-8")
    require("--runtime-file" in appimage_script, "AppImage build must pin its runtime stub")
    ET.parse(ROOT / "linux" / "appimage" / "memstrata-client.appdata.xml")

    flatpak = json.loads(
        (ROOT / "linux" / "flatpak" / "io.github.yadu9989.MemStrataClient.json.in").read_text(
            encoding="utf-8"
        )
        .replace("@RUNTIME_URL@", "https://invalid.example/runtime")
        .replace("@RUNTIME_SHA256@", "0" * 64)
        .replace("@RUNTIME_SIZE@", "1")
    )
    require(flatpak["id"] == PRODUCT["flatpak"]["app_id"], "Flatpak app ID mismatch")
    source = flatpak["modules"][0]["sources"][0]
    require(source["type"] == "extra-data", "Flatpak public manifest must use extra-data")

    forbidden_suffixes = {".exe", ".dll", ".dylib", ".so", ".msix", ".pkg", ".snap", ".AppImage"}
    ignored_parts = {"build", "dist", "parts", "payload", "prime", "stage"}
    leaked: list[str] = []
    unreadable: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in ignored_parts for part in relative.parts):
            continue
        try:
            is_file = path.is_file()
        except OSError as exc:
            unreadable.append(f"{relative}: {exc}")
            continue
        if is_file and path.suffix in forbidden_suffixes:
            leaked.append(str(relative))
    require(not leaked, f"binary/package artifacts must not be committed: {leaked}")
    require(not unreadable, f"packaging paths cannot be inspected: {unreadable}")
    print("packaging contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"packaging contract: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
