"""Stages a module's directories next to the built binary.

Each module stages its own content, so building a target brings in the content of
that target and whatever it links, and nothing else. A module that is not part of
the build does not put its files in the output directory.

Modules share the output directory - a library ships its shaders and every example
that uses it ships its own - so a module must not touch files it did not stage. The
manifest records what this module staged last time, which is what makes a deleted
source removable: it was staged before and no source provides it now. Files nobody
staged, or files another module staged, are none of this module's business and are
left alone.

Called from generated cmake, which bakes in the source directories it knows at
generate time. The files themselves are discovered here, at build time, so adding,
editing or deleting one takes effect on the next build with no re-configure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


class StagingError(RuntimeError):
    """Raised when the sources cannot be staged as they are."""


def collect_sources(source_dirs: list[Path]) -> dict[Path, Path]:
    """Maps each path relative to the destination to the file that provides it."""
    provided: dict[Path, Path] = {}
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            raise StagingError(f"Source directory does not exist: {source_dir}")

        for source_file in sorted(source_dir.rglob("*")):
            if not source_file.is_file():
                continue

            relative_path = source_file.relative_to(source_dir)
            previous = provided.get(relative_path)
            if previous is not None:
                # Both would be copied to the same place and the last one would win,
                # which is a coin toss decided by the order the directories are listed.
                raise StagingError(
                    f"'{relative_path}' is provided by two sources: {previous} and {source_file}"
                )
            provided[relative_path] = source_file

    return provided


def read_manifest(manifest: Path) -> set[Path]:
    """What this module staged last time. Empty when it has never staged anything."""
    if not manifest.is_file():
        return set()
    return {Path(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line}


def write_manifest(manifest: Path, staged: set[Path]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted(path.as_posix() for path in staged)
    manifest.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def is_outdated(source_file: Path, staged_file: Path) -> bool:
    if not staged_file.exists():
        return True
    # A staged file that is newer than its source is either already up to date or was
    # changed in place, and neither is worth overwriting.
    return source_file.stat().st_mtime_ns > staged_file.stat().st_mtime_ns


def prune_empty_parents(directory: Path, stop_at: Path) -> None:
    """Removes directories a deleted file left empty, up to but excluding stop_at."""
    while directory != stop_at and directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()
        directory = directory.parent


def stage_directories(destination: Path, source_dirs: list[Path], manifest: Path) -> tuple[int, int]:
    """Stages this module's sources into destination. Returns (copied, removed) counts."""
    provided = collect_sources(source_dirs)

    copied = 0
    for relative_path, source_file in provided.items():
        staged_file = destination / relative_path
        if not is_outdated(source_file, staged_file):
            continue
        staged_file.parent.mkdir(parents=True, exist_ok=True)
        # copy2 keeps the timestamp, so the staged file is never newer than its source
        # just because it was copied, and the next run has nothing to do.
        shutil.copy2(source_file, staged_file)
        copied += 1

    removed = 0
    for relative_path in sorted(read_manifest(manifest) - provided.keys()):
        staged_file = destination / relative_path
        if not staged_file.exists():
            continue
        staged_file.unlink()
        prune_empty_parents(staged_file.parent, destination)
        removed += 1

    write_manifest(manifest, set(provided.keys()))

    return copied, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a module's directories next to the built binary")
    parser.add_argument("--destination", required=True, type=Path, help="Directory to stage into")
    parser.add_argument(
        "--source",
        required=True,
        action="append",
        dest="sources",
        type=Path,
        help="Directory to stage from. Repeat to merge several.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="File recording what this module staged, so it can remove its own stale files",
    )
    args = parser.parse_args(argv)

    try:
        copied, removed = stage_directories(args.destination, args.sources, args.manifest)
    except StagingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    # Quiet when there was nothing to do, so a build that changes nothing says nothing.
    if copied or removed:
        print(f"staged {copied} file(s), removed {removed} file(s) in {args.destination}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
