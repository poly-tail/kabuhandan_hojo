"""Synchronize docs/*/current.md with the latest versioned files."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


VERSION_PATTERN = re.compile(r"_v(?P<version>\d+(?:\.\d+)*)\.md$")


@dataclass(frozen=True)
class CurrentFileSpec:
    current_path: Path
    version_glob: str
    version_label: str


def parse_version(filename: str) -> tuple[int, ...]:
    match = VERSION_PATTERN.search(filename)
    if not match:
        raise ValueError(f"Versioned file name is invalid: {filename}")
    return tuple(int(part) for part in match.group("version").split("."))


def discover_latest_file(current_file: Path, version_glob: str) -> Path:
    candidates = [path for path in current_file.parent.glob(version_glob) if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No versioned files matched {version_glob} next to {current_file}")
    return sorted(candidates, key=lambda path: parse_version(path.name), reverse=True)[0]


def sync_content(content: str, *, latest_filename: str, version_label: str) -> str:
    version_match = VERSION_PATTERN.search(latest_filename)
    if not version_match:
        raise ValueError(f"Version could not be parsed from {latest_filename}")
    version_text = f"v{version_match.group('version')}"
    updated = re.sub(
        r"^(> .*? )`[^`]+`$",
        lambda match: f"{match.group(1)}`{latest_filename}`",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    updated = re.sub(
        r"^> 現在の正本: `[^`]+`$",
        f"> 現在の正本: `{latest_filename}`",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    updated = re.sub(
        r"^(> .*? )`[^`]+`$",
        lambda match: f"{match.group(1)}`{latest_filename}`",
        updated,
        count=1,
        flags=re.MULTILINE,
    )
    updated = re.sub(
        rf"^- {re.escape(version_label)}: v\d+(?:\.\d+)*$",
        f"- {version_label}: {version_text}",
        updated,
        count=1,
        flags=re.MULTILINE,
    )
    return updated


def sync_file(spec: CurrentFileSpec, *, write: bool) -> bool:
    latest_file = discover_latest_file(spec.current_path, spec.version_glob)
    original = spec.current_path.read_text(encoding="utf-8")
    updated = sync_content(
        original,
        latest_filename=latest_file.name,
        version_label=spec.version_label,
    )
    changed = updated != original
    if changed and write:
        spec.current_path.write_text(updated, encoding="utf-8")
    return changed


def iter_specs(repo_root: Path) -> list[CurrentFileSpec]:
    return [
        CurrentFileSpec(
            current_path=repo_root / "docs" / "requirements" / "current.md",
            version_glob="requirements_v*.md",
            version_label="要件仕様書",
        ),
        CurrentFileSpec(
            current_path=repo_root / "docs" / "specs" / "current.md",
            version_glob="api_spec_v*.md",
            version_label="API仕様書",
        ),
        CurrentFileSpec(
            current_path=repo_root / "docs" / "screen_specs" / "current.md",
            version_glob="screen_spec_v*.md",
            version_label="画面仕様書",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write synchronized changes back to files.")
    parser.add_argument("--check", action="store_true", help="Only check for mismatches.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    write = args.write and not args.check

    changed_files: list[Path] = []
    for spec in iter_specs(repo_root):
        changed = sync_file(spec, write=write)
        if changed:
            changed_files.append(spec.current_path)

    if changed_files and not write:
        for path in changed_files:
            print(f"out-of-sync: {path}")
        return 1

    if changed_files:
        for path in changed_files:
            print(f"updated: {path}")
    else:
        print("all current.md files are synchronized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
