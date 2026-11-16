"""Rebuild the reviewed TV2+TV3 backend from original ZIPs and explicit patches.

Writes only to a new, empty output directory. Never deploys, accesses a database,
copies credentials, or uploads firmware. See docs/GHEP_LAI_TV2_TV3.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs/source-review/team-rebase-2026-11-15"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Unsafe relative path: {value}")
    if path.parts[:2] != ("backend", "app") or path.suffix != ".py":
        raise ValueError(f"Outside the reviewed Python backend: {value}")
    return Path(*path.parts)


def apply_hunks(base: bytes, changes: list[dict]) -> bytes:
    """Apply replacements at original line offsets; unchanged lines stay byte exact."""
    lines = base.decode("utf-8-sig").splitlines(keepends=True)
    result, cursor = [], 0
    for change in changes:
        start, end = change["start"], change["end"]
        if not 0 <= cursor <= start <= end <= len(lines):
            raise ValueError("Invalid or overlapping patch offsets")
        result.extend(lines[cursor:start])
        result.extend(change["lines"])
        cursor = end
    result.extend(lines[cursor:])
    return "".join(result).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tv2-zip", type=Path)
    parser.add_argument("--tv3-zip", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="Check current source against the reviewed result")
    args = parser.parse_args()
    manifest = json.loads((REVIEW / "manifest.json").read_text(encoding="utf-8"))
    patches = json.loads((REVIEW / "patches.json").read_text(encoding="utf-8"))
    if args.check:
        for row in manifest["files"]:
            path = ROOT / safe_relative(row["path"])
            if not path.is_file() or digest(path.read_bytes()) != row["result_sha256"]:
                raise SystemExit(f"Source differs from reviewed result: {row['path']}")
        for name in manifest["retired_paths"]:
            if (ROOT / safe_relative(name)).exists():
                raise SystemExit(f"Old flat module must not shadow its new package: {name}")
        expected = {row["path"] for row in manifest["files"]}
        actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / "backend/app").rglob("*.py")}
        if expected != actual:
            raise SystemExit("Backend file inventory differs from reviewed result")
        print(f"Verified {len(expected)} backend files against the reviewed integration.")
        return
    if not all((args.tv2_zip, args.tv3_zip, args.output)):
        parser.error("Supply --tv2-zip, --tv3-zip, --output, or use --check")
    output = args.output.resolve()
    if output == ROOT or output in ROOT.parents or (ROOT / "backend") in output.parents:
        parser.error("Output must be a separate directory, never the current backend or a parent")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Output must be empty; no existing files will be overwritten")
    archives = {"TV2": args.tv2_zip, "TV3": args.tv3_zip}
    for origin, path in archives.items():
        if digest(path.read_bytes()) != manifest["archives"][origin]["sha256"]:
            raise SystemExit(f"The {origin} archive does not match the reviewed original")
    # Validate and assemble everything before writing any output.
    results = {}
    with zipfile.ZipFile(args.tv2_zip) as tv2, zipfile.ZipFile(args.tv3_zip) as tv3:
        handles = {"TV2": tv2, "TV3": tv3}
        for row in manifest["files"]:
            relative = safe_relative(row["path"])
            base = handles[row["origin"]].read(row["archive_path"]) if row["origin"] in handles else b""
            if digest(base) != row["base_sha256"]:
                raise SystemExit(f"Original file hash mismatch: {row['path']}")
            content = apply_hunks(base, patches.get(row["path"], [])) if row["path"] in patches else base
            if digest(content) != row["result_sha256"]:
                raise SystemExit(f"Patched result hash mismatch: {row['path']}")
            results[relative] = content
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in results.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    print(f"Rebuilt {len(results)} backend files in {output}; nothing deployed.")


if __name__ == "__main__":
    main()
