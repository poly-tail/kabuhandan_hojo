"""Render Mermaid graphs or validate that generated SVGs are up to date."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def build_pairs(input_dir: Path, output_dir: Path) -> list[tuple[Path, Path]]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    sources = sorted(input_dir.glob("*.mmd"))
    if not sources:
        raise FileNotFoundError(f"No Mermaid source files found in: {input_dir}")
    return [(source, output_dir / f"{source.stem}.svg") for source in sources]


def stale_pairs(pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    return [
        (source, target)
        for source, target in pairs
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime
    ]


def resolve_npx() -> str:
    """Resolve an executable npx path across platforms."""

    candidates = ["npx.cmd", "npx"] if os.name == "nt" else ["npx"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("npx was not found. Install Node.js to render Mermaid graphs.")


def render_pairs(pairs: list[tuple[Path, Path]]) -> None:
    npx = resolve_npx()
    for source, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [npx, "-y", "@mermaid-js/mermaid-cli", "-i", str(source), "-o", str(target)],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--input-dir", default=str(repo_root / "docs" / "graphs" / "src"))
    parser.add_argument("--output-dir", default=str(repo_root / "docs" / "graphs" / "generated"))
    parser.add_argument("--check", action="store_true", help="Only verify that generated SVGs are fresh.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    pairs = build_pairs(input_dir=input_dir, output_dir=output_dir)
    stale = stale_pairs(pairs)
    if args.check:
        if stale:
            for source, target in stale:
                print(f"stale: {source} -> {target}")
            return 1
        print("all graph outputs are up to date")
        return 0

    render_pairs(stale or pairs)
    print(f"rendered {len(stale or pairs)} graph(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
