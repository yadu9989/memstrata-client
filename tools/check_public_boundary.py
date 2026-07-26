"""Fail when the public repository crosses the MemStrata IP boundary."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TOP_LEVEL = {
    ".github",
    ".gitattributes",
    ".gitignore",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "docs",
    "examples",
    "packaging",
    "pyproject.toml",
    "src",
    "tests",
    "tools",
}
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "eval",
    "harness",
    "memory_layer_pro",
    "memstrata_gep",
    "sandbox",
)
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".dll",
    ".dylib",
    ".exe",
    ".onnx",
    ".pdb",
    ".pem",
    ".pkl",
    ".prompt",
    ".so",
}
MAX_FILE_BYTES = 1_000_000


def _python_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise RuntimeError(f"unable to parse {path.relative_to(ROOT)}: {exc}") from exc
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def scan() -> list[str]:
    failures: list[str] = []
    for child in ROOT.iterdir():
        if child.name in IGNORED_PARTS:
            continue
        if child.name not in ALLOWED_TOP_LEVEL:
            failures.append(f"non-allowlisted top-level path: {child.name}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden artifact type: {relative}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            failures.append(f"cannot stat {relative}: {exc}")
            continue
        if size > MAX_FILE_BYTES:
            failures.append(f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        if path.suffix == ".py":
            try:
                imports = _python_imports(path)
            except RuntimeError as exc:
                failures.append(str(exc))
                continue
            for imported in imports:
                if any(
                    imported == prefix or imported.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    failures.append(f"proprietary import {imported!r} in {relative}")
    return failures


def main() -> int:
    failures = scan()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print("public boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
