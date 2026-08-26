"""Stages a module's directories next to the built binary.

Each module stages its own content, so building a target brings in the content of
that target and whatever it links, and nothing else. A module that is not part of
the build does not put its files in the output directory.

Modules share the output directory - a library ships its shaders and every example
that uses it ships its own - so a module must not touch files it did not stage. The
manifest records the destination paths assigned to this module, which is what makes
a deleted source removable: the path was staged before and no active source provides
it now. Files nobody staged, or files assigned to another module, are left alone.

Called from generated cmake, which bakes in the source directories it knows at
generate time. The files themselves are discovered here, at build time, so adding,
editing or deleting one takes effect on the next build with no re-configure.
"""

from __future__ import annotations

import argparse
import errno
import os
import shutil
import stat
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator


_LOCK_RETRY_SECONDS = 0.05
_PLAN_HEADER = "YAE-STAGING-PLAN\t1"
_LEGACY_MIGRATION_MARKER = "legacy-manifests-migrated"


class StagingError(RuntimeError):
    """Raised when the sources cannot be staged as they are."""


def is_path_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


@contextmanager
def destination_lock(destination: Path) -> Iterator[None]:
    if is_path_link(destination.parent) or (
        destination.parent.exists() and not destination.parent.is_dir()
    ):
        raise StagingError(f"Cannot use staging lock directory: {destination.parent}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.stage.lock"
    if is_path_link(lock_path) or (lock_path.exists() and not lock_path.is_file()):
        raise StagingError(f"Cannot use staging lock file: {lock_path}")
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(_LOCK_RETRY_SECONDS)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
    """Destination paths assigned to this module. Empty before it owns any."""
    if is_path_link(manifest):
        raise StagingError(f"Cannot use linked staging manifest: {manifest}")
    if not manifest.exists():
        return set()
    if not manifest.is_file():
        raise StagingError(f"Cannot use non-file staging manifest: {manifest}")
    result: set[Path] = set()
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise StagingError(f"Cannot decode staging manifest: {manifest}") from error
    for line in lines:
        if not line:
            continue
        relative_path = Path(line)
        validate_relative_path(relative_path)
        result.add(relative_path)
    return result


def write_text_atomically(path: Path, text: str) -> None:
    if is_path_link(path.parent) or (path.parent.exists() and not path.parent.is_dir()):
        raise StagingError(f"Cannot use staging state directory: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_manifest(manifest: Path, staged: set[Path]) -> None:
    lines = sorted(path.as_posix() for path in staged)
    write_text_atomically(manifest, "".join(f"{line}\n" for line in lines))


def validate_relative_path(relative_path: Path) -> None:
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise StagingError(f"Invalid staged relative path: {relative_path}")


def staging_manifest_path(manifest_root: Path, relative_path: Path) -> Path:
    validate_relative_path(relative_path)
    if len(relative_path.parts) != 2 or relative_path.suffix != ".manifest":
        raise StagingError(f"Invalid active staging manifest path: {relative_path}")
    state_directory = manifest_root / relative_path.parts[0]
    if is_path_link(state_directory) or (
        state_directory.exists() and not state_directory.is_dir()
    ):
        raise StagingError(f"Cannot use staging state directory: {state_directory}")
    return (manifest_root / relative_path).absolute()


def parse_staging_plan(
    manifest_root: Path, lines: list[str], plan_description: Path
) -> dict[Path, list[Path]]:
    if not lines or lines[0] != _PLAN_HEADER:
        raise StagingError(f"Incomplete active staging manifest plan: {plan_description}")

    result: dict[Path, list[Path]] = {}
    current_manifest: Path | None = None
    for line in lines[1:-1]:
        kind, separator, value = line.partition("\t")
        if not separator or not value:
            raise StagingError(f"Invalid active staging manifest plan entry: {line}")
        if kind == "manifest":
            current_manifest = staging_manifest_path(manifest_root, Path(value))
            if current_manifest in result:
                raise StagingError(f"Duplicate active staging manifest: {current_manifest}")
            result[current_manifest] = []
        elif kind == "source" and current_manifest is not None:
            source = Path(value)
            if not source.is_absolute():
                raise StagingError(f"Staging source path must be absolute: {source}")
            result[current_manifest].append(source)
        else:
            raise StagingError(f"Invalid active staging manifest plan entry: {line}")

    footer_kind, separator, footer_value = lines[-1].partition("\t")
    if footer_kind != "end" or not separator or not footer_value.isdigit():
        raise StagingError(f"Incomplete active staging manifest plan: {plan_description}")
    if int(footer_value) != len(result) or any(not sources for sources in result.values()):
        raise StagingError(f"Incomplete active staging manifest plan: {plan_description}")
    return result


def read_staging_plan(manifest_root: Path, active_manifests: Path) -> dict[Path, list[Path]]:
    if is_path_link(manifest_root) or not manifest_root.is_dir():
        raise StagingError(f"Cannot use staging manifest root: {manifest_root}")
    if is_path_link(active_manifests) or not active_manifests.is_file():
        raise StagingError(f"Cannot read active staging manifests: {active_manifests}")

    try:
        lines = active_manifests.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise StagingError(f"Cannot decode active staging manifests: {active_manifests}") from error
    return parse_staging_plan(manifest_root, lines, active_manifests)


def write_staging_plan(
    manifest_root: Path, active_manifests: Path, entries: list[str]
) -> None:
    manifest_root = manifest_root.absolute()
    active_manifests = active_manifests.absolute()
    if active_manifests.parent != manifest_root:
        raise StagingError(
            "The active staging manifest list must be inside the staging manifest root"
        )
    if is_path_link(manifest_root) or (
        manifest_root.exists() and not manifest_root.is_dir()
    ):
        raise StagingError(f"Cannot use staging manifest root: {manifest_root}")
    with destination_lock(manifest_root.parent / "yae-staging-state"):
        if is_path_link(manifest_root) or (
            manifest_root.exists() and not manifest_root.is_dir()
        ):
            raise StagingError(f"Cannot use staging manifest root: {manifest_root}")
        manifest_root.mkdir(parents=True, exist_ok=True)
        lines = [_PLAN_HEADER, *entries]
        manifest_count = sum(entry.startswith("manifest\t") for entry in entries)
        lines.append(f"end\t{manifest_count}")
        parse_staging_plan(manifest_root, lines, active_manifests)
        write_text_atomically(active_manifests, "".join(f"{line}\n" for line in lines))


def ensure_destination_root(destination_root: Path) -> None:
    if is_path_link(destination_root) or (
        destination_root.exists() and not destination_root.is_dir()
    ):
        raise StagingError(f"Cannot use staging destination root: {destination_root}")
    destination_root.mkdir(parents=True, exist_ok=True)


def prepare_destination_root(destination_root: Path, destination: Path) -> None:
    ensure_destination_root(destination_root)
    try:
        relative_destination = destination.absolute().relative_to(destination_root.absolute())
    except ValueError as error:
        raise StagingError(
            f"Staging destination must be inside {destination_root}: {destination}"
        ) from error
    if len(relative_destination.parts) != 1:
        raise StagingError(f"Invalid staging destination: {destination}")


def collect_manifest_owners(manifests: set[Path], excluded: Path | None = None) -> dict[Path, Path]:
    owners: dict[Path, Path] = {}
    for manifest in sorted(manifests):
        if manifest == excluded:
            continue
        for relative_path in read_manifest(manifest):
            previous = owners.get(relative_path)
            if previous is not None:
                raise StagingError(
                    f"'{relative_path}' is owned by two staging manifests: "
                    f"{previous} and {manifest}"
                )
            owners[relative_path] = manifest
    return owners


def needs_copy(source_file: Path, staged_file: Path) -> bool:
    if is_path_link(staged_file) or not staged_file.is_file():
        return True
    source_stat = source_file.stat()
    staged_stat = staged_file.stat()
    if source_stat.st_size != staged_stat.st_size:
        return True
    if stat.S_IMODE(source_stat.st_mode) != stat.S_IMODE(staged_stat.st_mode):
        return True

    with source_file.open("rb") as source, staged_file.open("rb") as staged:
        while source_chunk := source.read(1024 * 1024):
            if staged.read(len(source_chunk)) != source_chunk:
                return True

    return False


def prepare_staging_parent(destination: Path, relative_path: Path, create_missing: bool) -> bool:
    validate_relative_path(relative_path)
    if is_path_link(destination) or (destination.exists() and not destination.is_dir()):
        raise StagingError(f"Cannot use non-directory staging destination: {destination}")
    if not destination.exists():
        if not create_missing:
            return False
        destination.mkdir(parents=True)

    parent = destination
    for part in relative_path.parent.parts:
        parent /= part
        if is_path_link(parent) or (parent.exists() and not parent.is_dir()):
            raise StagingError(f"Cannot use non-directory staged path: {parent}")
        if not parent.exists():
            if not create_missing:
                return False
            parent.mkdir()
    return True


def prune_empty_parents(directory: Path, stop_at: Path) -> None:
    """Removes directories a deleted file left empty, up to but excluding stop_at."""
    while directory != stop_at and directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()
        directory = directory.parent


def remove_staged_file(destination: Path, relative_path: Path) -> bool:
    if not prepare_staging_parent(destination, relative_path, create_missing=False):
        return False
    staged_file = destination / relative_path
    if not staged_file.exists() and not is_path_link(staged_file):
        return False
    if staged_file.is_junction() or (not staged_file.is_symlink() and not staged_file.is_file()):
        raise StagingError(f"Cannot remove non-file staged path: {staged_file}")
    staged_file.unlink()
    prune_empty_parents(staged_file.parent, destination)
    return True


def stage_directories(
    destination: Path,
    source_dirs: list[Path],
    manifest: Path,
    active_manifests_file: Path | None = None,
    destination_root: Path | None = None,
) -> tuple[int, int]:
    """Stages this module's sources into destination. Returns (copied, removed) counts."""
    provided = collect_sources(source_dirs)
    destination_root = destination.parent if destination_root is None else destination_root
    prepare_destination_root(destination_root, destination)

    with ExitStack() as locks:
        if active_manifests_file is not None:
            manifest_root = active_manifests_file.parent.absolute()
            locks.enter_context(
                destination_lock(manifest_root.parent / "yae-staging-state")
            )
        locks.enter_context(destination_lock(destination))
        other_owners: dict[Path, Path] = {}
        if active_manifests_file is not None:
            staging_plan = read_staging_plan(manifest_root, active_manifests_file)
            manifest = manifest.absolute()
            if manifest not in staging_plan:
                raise StagingError(f"Staging manifest is not active in this project: {manifest}")
            planned_sources = {source.absolute() for source in staging_plan[manifest]}
            if planned_sources != {source.absolute() for source in source_dirs}:
                raise StagingError(
                    f"Staging sources do not match the active project plan: {manifest}"
                )
            other_owners = collect_manifest_owners(set(staging_plan), excluded=manifest)
        return stage_collected_sources(destination, provided, manifest, other_owners)


def stage_collected_sources(
    destination: Path,
    provided: dict[Path, Path],
    manifest: Path,
    other_owners: dict[Path, Path],
) -> tuple[int, int]:
    """Updates a destination while its destination lock is held."""

    collisions = sorted(provided.keys() & other_owners.keys())
    if collisions:
        relative_path = collisions[0]
        raise StagingError(
            f"'{relative_path}' is already staged by another module: {other_owners[relative_path]}"
        )

    copied = 0
    for relative_path, source_file in provided.items():
        prepare_staging_parent(destination, relative_path, create_missing=True)
        staged_file = destination / relative_path
        if not needs_copy(source_file, staged_file):
            continue
        if staged_file.is_symlink():
            staged_file.unlink()
        elif staged_file.is_junction():
            raise StagingError(f"Cannot replace non-file staged path: {staged_file}")
        elif staged_file.exists() and not staged_file.is_file():
            raise StagingError(f"Cannot replace non-file staged path: {staged_file}")
        shutil.copy2(source_file, staged_file)
        copied += 1

    removed = 0
    for relative_path in sorted(read_manifest(manifest) - provided.keys()):
        if relative_path in other_owners:
            continue
        if remove_staged_file(destination, relative_path):
            removed += 1

    write_manifest(manifest, set(provided.keys()))

    return copied, removed


def collect_current_owners(
    staging_plan: dict[Path, list[Path]],
) -> dict[str, dict[Path, Path]]:
    owners_by_destination: dict[str, dict[Path, Path]] = {}
    for manifest, source_dirs in sorted(staging_plan.items()):
        owners = owners_by_destination.setdefault(manifest.parent.name, {})
        for relative_path in collect_sources(source_dirs):
            previous = owners.get(relative_path)
            if previous is not None:
                raise StagingError(
                    f"'{relative_path}' is provided by two active staging modules: "
                    f"{previous} and {manifest}"
                )
            owners[relative_path] = manifest
    return owners_by_destination


def find_existing_manifests(manifest_root: Path, active_manifests_file: Path) -> set[Path]:
    result: set[Path] = set()
    for destination_state in sorted(manifest_root.iterdir()):
        if destination_state == active_manifests_file:
            continue
        if is_path_link(destination_state):
            raise StagingError(f"Cannot use linked staging state directory: {destination_state}")
        if not destination_state.is_dir():
            continue
        for manifest in destination_state.glob("*.manifest"):
            result.add(manifest.absolute())
    return result


def legacy_manifest_destination(manifest: Path) -> str | None:
    if manifest.suffix != ".manifest":
        return None
    stem = manifest.name.removesuffix(".manifest")
    target, separator, destination = stem.rpartition("_copy_files_")
    if not separator or not target or not destination:
        return None
    relative_destination = Path(destination)
    validate_relative_path(relative_destination)
    if len(relative_destination.parts) != 1:
        raise StagingError(f"Invalid legacy staging manifest name: {manifest}")
    return destination


def find_legacy_manifests(
    legacy_manifest_root: Path, migration_marker: Path
) -> dict[str, set[Path]]:
    if is_path_link(migration_marker) or (
        migration_marker.exists() and not migration_marker.is_file()
    ):
        raise StagingError(f"Cannot use staging migration marker: {migration_marker}")
    if migration_marker.is_file():
        return {}
    if not legacy_manifest_root.exists():
        return {}
    if is_path_link(legacy_manifest_root) or not legacy_manifest_root.is_dir():
        raise StagingError(f"Cannot use legacy staging manifest root: {legacy_manifest_root}")

    result: dict[str, set[Path]] = {}

    def raise_walk_error(error: OSError) -> None:
        raise StagingError(
            f"Cannot search legacy staging manifests in {legacy_manifest_root}: {error}"
        ) from error

    for directory, directory_names, file_names in os.walk(
        legacy_manifest_root, onerror=raise_walk_error
    ):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if is_path_link(child):
                raise StagingError(f"Cannot search linked legacy staging directory: {child}")
        for file_name in file_names:
            manifest = directory_path / file_name
            destination = legacy_manifest_destination(manifest)
            if destination is not None:
                result.setdefault(destination, set()).add(manifest)
    return result


def reconcile_staging(
    destination_root: Path,
    manifest_root: Path,
    active_manifests_file: Path,
    legacy_manifest_root: Path | None = None,
) -> tuple[int, int]:
    manifest_root = manifest_root.absolute()
    active_manifests_file = active_manifests_file.absolute()
    if not manifest_root.exists() and not active_manifests_file.exists():
        return 0, 0
    if active_manifests_file.parent.absolute() != manifest_root:
        raise StagingError(
            "The active staging manifest list must be inside the staging manifest root"
        )
    ensure_destination_root(destination_root)
    with destination_lock(manifest_root.parent / "yae-staging-state"):
        return reconcile_staging_locked(
            destination_root,
            manifest_root,
            active_manifests_file,
            legacy_manifest_root,
        )


def reconcile_staging_locked(
    destination_root: Path,
    manifest_root: Path,
    active_manifests_file: Path,
    legacy_manifest_root: Path | None,
) -> tuple[int, int]:
    staging_plan = read_staging_plan(manifest_root, active_manifests_file)
    existing_manifests = find_existing_manifests(manifest_root, active_manifests_file)
    migration_marker = manifest_root / _LEGACY_MIGRATION_MARKER
    legacy_manifests = (
        find_legacy_manifests(legacy_manifest_root, migration_marker)
        if legacy_manifest_root is not None
        else {}
    )

    destinations = sorted(
        {manifest.parent.name for manifest in set(staging_plan) | existing_manifests}
        | set(legacy_manifests)
    )
    for destination_name in destinations:
        prepare_destination_root(destination_root, destination_root / destination_name)

    removed_files = 0
    removed_manifests = 0
    with ExitStack() as locks:
        for destination_name in destinations:
            locks.enter_context(destination_lock(destination_root / destination_name))

        current_owners = collect_current_owners(staging_plan)
        historical_paths: dict[str, set[Path]] = {name: set() for name in destinations}
        for manifest in existing_manifests:
            historical_paths[manifest.parent.name].update(read_manifest(manifest))
        for destination_name, manifests in legacy_manifests.items():
            for manifest in manifests:
                historical_paths[destination_name].update(read_manifest(manifest))

        desired_manifests: dict[Path, set[Path]] = {
            manifest: set() for manifest in staging_plan
        }
        for destination_name in destinations:
            destination = destination_root / destination_name
            owners = current_owners.get(destination_name, {})
            for relative_path in sorted(historical_paths[destination_name]):
                owner = owners.get(relative_path)
                if owner is not None:
                    desired_manifests[owner].add(relative_path)
                elif remove_staged_file(destination, relative_path):
                    removed_files += 1

        for manifest, paths in sorted(desired_manifests.items()):
            write_manifest(manifest, paths)

        for stale_manifest in sorted(existing_manifests - staging_plan.keys()):
            stale_manifest.unlink()
            removed_manifests += 1
        for manifests in legacy_manifests.values():
            for manifest in sorted(manifests):
                manifest.unlink()
                removed_manifests += 1

        for destination_name in destinations:
            state_directory = manifest_root / destination_name
            if state_directory.is_dir() and not any(state_directory.iterdir()):
                state_directory.rmdir()

    if legacy_manifest_root is not None:
        write_text_atomically(migration_marker, "complete\n")

    if not staging_plan:
        active_manifests_file.unlink(missing_ok=True)
        migration_marker.unlink(missing_ok=True)
        if manifest_root.is_dir() and not any(manifest_root.iterdir()):
            manifest_root.rmdir()

    return removed_files, removed_manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage a module's directories next to the built binary"
    )
    parser.add_argument("--destination", type=Path, help="Directory to stage into")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        type=Path,
        help="Directory to stage from. Repeat to merge several.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="File recording what this module staged, so it can remove its own stale files",
    )
    parser.add_argument(
        "--active-manifests", type=Path, help="Generated list of active staging manifests"
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Remove staging state for modules no longer generated",
    )
    parser.add_argument(
        "--write-plan",
        action="store_true",
        help="Atomically publish the generated staging ownership plan",
    )
    parser.add_argument(
        "--plan-entry",
        action="append",
        dest="plan_entries",
        default=[],
        help="Generated manifest or source entry. Repeat for every entry.",
    )
    parser.add_argument(
        "--destination-root", type=Path, help="Parent of all staged destination directories"
    )
    parser.add_argument("--manifest-root", type=Path, help="Shared staging manifest directory")
    parser.add_argument(
        "--legacy-manifest-root", type=Path, help="Previous per-module manifest directory"
    )
    args = parser.parse_args(argv)

    try:
        if args.write_plan:
            if args.manifest_root is None or args.active_manifests is None:
                parser.error("--write-plan requires --manifest-root and --active-manifests")
            write_staging_plan(args.manifest_root, args.active_manifests, args.plan_entries)
            return 0

        if args.reconcile:
            if (
                args.destination_root is None
                or args.manifest_root is None
                or args.active_manifests is None
            ):
                parser.error(
                    "--reconcile requires --destination-root, --manifest-root, and "
                    "--active-manifests"
                )
            removed, retired = reconcile_staging(
                args.destination_root,
                args.manifest_root,
                args.active_manifests,
                args.legacy_manifest_root,
            )
            if removed or retired:
                print(f"removed {removed} stale staged file(s) from {retired} retired module(s)")
            return 0

        if args.destination is None or args.sources is None or args.manifest is None:
            parser.error("staging requires --destination, --source, and --manifest")
        copied, removed = stage_directories(
            args.destination,
            args.sources,
            args.manifest,
            args.active_manifests,
            args.destination_root,
        )
    except (OSError, StagingError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    # Quiet when there was nothing to do, so a build that changes nothing says nothing.
    if copied or removed:
        print(f"staged {copied} file(s), removed {removed} file(s) in {args.destination}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
