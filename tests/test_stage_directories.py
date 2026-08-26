"""Unit tests for the generated-project staging script."""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest

@pytest.fixture(scope="module")
def staging() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "stage_directories.py"
    spec = importlib.util.spec_from_file_location("stage_directories", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_older(path: Path, seconds: int = 10) -> None:
    """Backdates a file so staging sees it as older than what is already staged."""
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


def manifest(tmp_path: Path, name: str = "module") -> Path:
    return tmp_path / "build" / f"{name}.manifest"


def write_active_manifest_plan(plan: Path, entries: dict[str, list[Path]]) -> None:
    lines = ["YAE-STAGING-PLAN\t1"]
    for relative_manifest, sources in entries.items():
        lines.append(f"manifest\t{relative_manifest}")
        lines.extend(f"source\t{source.absolute()}" for source in sources)
    lines.append(f"end\t{len(entries)}")
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")


def active_manifest_plan(tmp_path: Path, entries: dict[str, list[Path]]) -> Path:
    root = tmp_path / "build" / ".yae-staging"
    root.mkdir(parents=True, exist_ok=True)
    plan = root / "active-manifests.txt"
    write_active_manifest_plan(plan, entries)
    return plan


def stage_current_project(
    staging,
    tmp_path: Path,
    destination: Path,
    sources: list[Path],
) -> tuple[int, int]:
    relative_manifest = f"{destination.name}/module.manifest"
    plan = active_manifest_plan(tmp_path, {relative_manifest: sources})
    return staging.stage_directories(
        destination,
        sources,
        plan.parent / relative_manifest,
        plan,
        destination.parent,
    )


def staged_files(destination: Path) -> set[str]:
    return {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}


def test_sources_are_copied_into_the_destination(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "shaders/a.frag", "a")
    write(source / "shaders/nested/b.vert", "b")
    destination = tmp_path / "out"

    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert staged_files(destination) == {"shaders/a.frag", "shaders/nested/b.vert"}
    assert (destination / "shaders/nested/b.vert").read_text(encoding="utf-8") == "b"
    assert (copied, removed) == (2, 0)


def test_several_sources_are_merged_into_one_destination(staging, tmp_path: Path) -> None:
    """A module can declare more than one directory staged to the same place."""
    library = tmp_path / "library"
    write(library / "shaders/lib/a.frag", "a")
    example = tmp_path / "example"
    write(example / "shaders/example/b.frag", "b")
    destination = tmp_path / "out"

    staging.stage_directories(destination, [library, example], manifest(tmp_path))

    assert staged_files(destination) == {"shaders/lib/a.frag", "shaders/example/b.frag"}


def test_staging_again_does_nothing(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "a.frag", "a")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))
    stamp_before = (destination / "a.frag").stat().st_mtime_ns

    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert (copied, removed) == (0, 0)
    assert (destination / "a.frag").stat().st_mtime_ns == stamp_before


def test_changed_source_is_restaged(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "a.frag", "before")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))

    write(source / "a.frag", "after")
    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert (destination / "a.frag").read_text(encoding="utf-8") == "after"
    assert (copied, removed) == (1, 0)
    assert source_file.exists()


def test_deleted_source_is_removed_from_the_destination(staging, tmp_path: Path) -> None:
    """A file whose source is gone would otherwise still be found by whatever runs
    from the destination."""
    source = tmp_path / "source"
    write(source / "keep.frag", "keep")
    removed_file = write(source / "gone.frag", "gone")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))

    removed_file.unlink()
    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert staged_files(destination) == {"keep.frag"}
    assert (copied, removed) == (0, 1)


def test_a_module_does_not_remove_another_modules_files(staging, tmp_path: Path) -> None:
    """The whole point of the manifest. Modules stage into one directory, so a module
    deleting everything its own sources do not provide would take the other modules'
    files with it."""
    library = tmp_path / "library"
    write(library / "shaders/lib/a.frag", "a")
    example = tmp_path / "example"
    write(example / "shaders/example/b.frag", "b")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [library], manifest(tmp_path, "library"))
    staging.stage_directories(destination, [example], manifest(tmp_path, "example"))

    # The library stages again, knowing nothing about the example's file.
    copied, removed = staging.stage_directories(destination, [library], manifest(tmp_path, "library"))

    assert staged_files(destination) == {"shaders/lib/a.frag", "shaders/example/b.frag"}
    assert (copied, removed) == (0, 0)


def test_a_module_removes_only_its_own_stale_files(staging, tmp_path: Path) -> None:
    library = tmp_path / "library"
    library_file = write(library / "shaders/lib/a.frag", "a")
    example = tmp_path / "example"
    write(example / "shaders/example/b.frag", "b")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [library], manifest(tmp_path, "library"))
    staging.stage_directories(destination, [example], manifest(tmp_path, "example"))

    library_file.unlink()
    copied, removed = staging.stage_directories(destination, [library], manifest(tmp_path, "library"))

    assert staged_files(destination) == {"shaders/example/b.frag"}
    assert (copied, removed) == (0, 1)


def test_reconciliation_removes_retired_module_content(staging, tmp_path: Path) -> None:
    library = tmp_path / "library"
    example = tmp_path / "example"
    write(library / "library.txt", "library")
    write(example / "example.txt", "example")
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    plan = active_manifest_plan(
        tmp_path,
        {"content/library.manifest": [library], "content/example.manifest": [example]},
    )
    library_manifest = plan.parent / "content/library.manifest"
    example_manifest = plan.parent / "content/example.manifest"
    staging.stage_directories(destination, [library], library_manifest, plan)
    staging.stage_directories(destination, [example], example_manifest, plan)
    write(destination / "handwritten.txt", "handwritten")
    write_active_manifest_plan(plan, {"content/library.manifest": [library]})

    removed, retired = staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (removed, retired) == (1, 1)
    assert staged_files(destination) == {"library.txt", "handwritten.txt"}
    assert library_manifest.is_file()
    assert not example_manifest.exists()


def test_reconciliation_preserves_an_active_legacy_owner(staging, tmp_path: Path) -> None:
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    write(destination / "shared.txt", "active")
    active_source = tmp_path / "active"
    write(active_source / "shared.txt", "active")
    plan = active_manifest_plan(tmp_path, {"content/active.manifest": [active_source]})
    active_manifest = plan.parent / "content/active.manifest"
    retired_manifest = plan.parent / "content/retired.manifest"
    staging.write_manifest(active_manifest, {Path("shared.txt")})
    staging.write_manifest(retired_manifest, {Path("shared.txt")})

    removed, retired = staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (removed, retired) == (0, 1)
    assert (destination / "shared.txt").read_text(encoding="utf-8") == "active"
    assert not retired_manifest.exists()


def test_reconciliation_removes_the_last_staging_module(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "old.txt", "old")
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    plan = active_manifest_plan(tmp_path, {"content/old.manifest": [source]})
    old_manifest = plan.parent / "content/old.manifest"
    staging.stage_directories(destination, [source], old_manifest, plan)
    write_active_manifest_plan(plan, {})

    removed, retired = staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (removed, retired) == (1, 1)
    assert not (destination / "old.txt").exists()
    assert not old_manifest.parent.exists()
    assert staging.reconcile_staging(destination_root, plan.parent, plan) == (0, 0)


def test_reconciliation_rejects_active_duplicate_ownership_before_cleanup(staging, tmp_path: Path) -> None:
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    write(destination / "shared.txt", "shared")
    write(destination / "stale.txt", "stale")
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    write(first_source / "shared.txt", "first")
    write(second_source / "shared.txt", "second")
    plan = active_manifest_plan(
        tmp_path,
        {"content/first.manifest": [first_source], "content/second.manifest": [second_source]},
    )
    staging.write_manifest(plan.parent / "content/first.manifest", {Path("shared.txt")})
    staging.write_manifest(plan.parent / "content/second.manifest", {Path("shared.txt")})
    staging.write_manifest(plan.parent / "content/retired.manifest", {Path("stale.txt")})

    with pytest.raises(staging.StagingError, match="provided by two active staging modules"):
        staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (destination / "stale.txt").is_file()
    assert (plan.parent / "content/retired.manifest").is_file()


def test_interrupted_reconciliation_is_retryable(staging, tmp_path: Path, monkeypatch) -> None:
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    write(destination / "stale.txt", "stale")
    plan = active_manifest_plan(tmp_path, {})
    retired_manifest = plan.parent / "content/retired.manifest"
    staging.write_manifest(retired_manifest, {Path("stale.txt")})
    original_unlink = Path.unlink

    def interrupt_manifest_removal(path: Path, *args, **kwargs) -> None:
        if path == retired_manifest:
            raise KeyboardInterrupt
        original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch_context:
        patch_context.setattr(Path, "unlink", interrupt_manifest_removal)
        with pytest.raises(KeyboardInterrupt):
            staging.reconcile_staging(destination_root, plan.parent, plan)

    assert not (destination / "stale.txt").exists()
    assert retired_manifest.is_file()
    assert staging.reconcile_staging(destination_root, plan.parent, plan) == (0, 1)
    assert not retired_manifest.exists()


def test_reconciliation_transfers_ownership_before_the_new_owner_stages(
    staging, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_file = write(first / "shared.txt", "first")
    second.mkdir()
    destination_root = tmp_path / "out"
    destination = destination_root / "content"
    plan = active_manifest_plan(
        tmp_path,
        {"content/first.manifest": [first], "content/second.manifest": [second]},
    )
    first_manifest = plan.parent / "content/first.manifest"
    second_manifest = plan.parent / "content/second.manifest"
    staging.stage_directories(destination, [first], first_manifest, plan, destination_root)

    first_file.unlink()
    write(second / "shared.txt", "second")
    staging.reconcile_staging(destination_root, plan.parent, plan)

    copied, removed = staging.stage_directories(
        destination, [second], second_manifest, plan, destination_root
    )

    assert (copied, removed) == (1, 0)
    assert (destination / "shared.txt").read_text(encoding="utf-8") == "second"
    assert staging.read_manifest(first_manifest) == set()
    assert staging.read_manifest(second_manifest) == {Path("shared.txt")}


def test_reconciliation_validates_every_destination_before_cleanup(staging, tmp_path: Path) -> None:
    alpha_source = tmp_path / "alpha-source"
    beta_first = tmp_path / "beta-first"
    beta_second = tmp_path / "beta-second"
    write(beta_first / "shared.txt", "first")
    write(beta_second / "shared.txt", "second")
    destination_root = tmp_path / "out"
    write(destination_root / "alpha/stale.txt", "stale")
    plan = active_manifest_plan(
        tmp_path,
        {
            "alpha/active.manifest": [alpha_source],
            "beta/first.manifest": [beta_first],
            "beta/second.manifest": [beta_second],
        },
    )
    alpha_source.mkdir()
    retired_manifest = plan.parent / "alpha/retired.manifest"
    staging.write_manifest(retired_manifest, {Path("stale.txt")})

    with pytest.raises(staging.StagingError, match="provided by two active staging modules"):
        staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (destination_root / "alpha/stale.txt").is_file()
    assert retired_manifest.is_file()


def test_reconciliation_migrates_legacy_manifests(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "kept.txt", "source")
    destination_root = tmp_path / "out"
    write(destination_root / "content/kept.txt", "staged")
    write(destination_root / "content/retired.txt", "retired")
    plan = active_manifest_plan(tmp_path, {"content/active_copy_files.manifest": [source]})
    legacy_root = tmp_path / "build/yae_modules"
    active_legacy = legacy_root / "module/active_copy_files_content.manifest"
    retired_legacy = legacy_root / "old/retired_copy_files_content.manifest"
    staging.write_manifest(active_legacy, {Path("kept.txt")})
    staging.write_manifest(retired_legacy, {Path("retired.txt")})

    removed, retired = staging.reconcile_staging(
        destination_root, plan.parent, plan, legacy_root
    )

    assert (removed, retired) == (1, 2)
    assert (destination_root / "content/kept.txt").read_text(encoding="utf-8") == "staged"
    assert not (destination_root / "content/retired.txt").exists()
    assert staging.read_manifest(plan.parent / "content/active_copy_files.manifest") == {
        Path("kept.txt")
    }
    assert not active_legacy.exists()
    assert not retired_legacy.exists()


def test_reconciliation_removes_legacy_only_final_owner(staging, tmp_path: Path) -> None:
    destination_root = tmp_path / "build/bin"
    staged_file = write(destination_root / "content/retired.txt", "retired")
    legacy_manifest = tmp_path / "build/yae_modules/old/retired_copy_files_content.manifest"
    staging.write_manifest(legacy_manifest, {Path("retired.txt")})
    manifest_root = tmp_path / "build/.yae-staging"
    plan = manifest_root / "active-manifests.txt"
    staging.write_staging_plan(manifest_root, plan, [])

    removed, retired = staging.reconcile_staging(
        destination_root,
        manifest_root,
        plan,
        tmp_path / "build/yae_modules",
    )

    assert (removed, retired) == (1, 1)
    assert not staged_file.exists()
    assert not legacy_manifest.exists()
    assert not manifest_root.exists()


def test_plan_publication_replaces_a_symlink_without_touching_its_target(
    staging, tmp_path: Path
) -> None:
    manifest_root = tmp_path / "build/.yae-staging"
    manifest_root.mkdir(parents=True)
    source = tmp_path / "source"
    source.mkdir()
    outside = write(tmp_path / "outside.txt", "untouched")
    plan = manifest_root / "active-manifests.txt"
    plan.symlink_to(outside)

    staging.write_staging_plan(
        manifest_root,
        plan,
        ["manifest\tcontent/module.manifest", f"source\t{source.absolute()}"],
    )

    assert outside.read_text(encoding="utf-8") == "untouched"
    assert not plan.is_symlink()
    assert list(staging.read_staging_plan(manifest_root, plan).values()) == [[source.absolute()]]


def test_plan_publication_rejects_a_junction_root(
    staging, tmp_path: Path, monkeypatch
) -> None:
    manifest_root = tmp_path / "build/.yae-staging"
    original_is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == manifest_root or original_is_junction(path),
    )

    with pytest.raises(staging.StagingError, match="Cannot use staging manifest root"):
        staging.write_staging_plan(
            manifest_root,
            manifest_root / "active-manifests.txt",
            [],
        )

    assert not manifest_root.exists()


def test_reconciliation_rejects_a_junction_in_legacy_state(
    staging, tmp_path: Path, monkeypatch
) -> None:
    destination_root = tmp_path / "build/bin"
    plan = active_manifest_plan(tmp_path, {})
    legacy_root = tmp_path / "build/yae_modules"
    linked_directory = legacy_root / "linked"
    linked_directory.mkdir(parents=True)
    original_is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == linked_directory or original_is_junction(path),
    )

    with pytest.raises(staging.StagingError, match="linked legacy staging directory"):
        staging.reconcile_staging(destination_root, plan.parent, plan, legacy_root)


def test_reconciliation_rejects_an_incomplete_plan_before_cleanup(staging, tmp_path: Path) -> None:
    destination_root = tmp_path / "out"
    write(destination_root / "content/stale.txt", "stale")
    plan = active_manifest_plan(tmp_path, {})
    retired_manifest = plan.parent / "content/retired.manifest"
    staging.write_manifest(retired_manifest, {Path("stale.txt")})
    plan.write_text("YAE-STAGING-PLAN\t1\n", encoding="utf-8")

    with pytest.raises(staging.StagingError, match="Incomplete active staging manifest plan"):
        staging.reconcile_staging(destination_root, plan.parent, plan)

    assert (destination_root / "content/stale.txt").is_file()
    assert retired_manifest.is_file()


def test_staging_rejects_a_symlinked_destination_root(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "escape.txt", "escape")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination_root = tmp_path / "build/bin"
    destination_root.parent.mkdir(parents=True)
    destination_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(staging.StagingError, match="Cannot use staging destination root"):
        staging.stage_directories(
            destination_root / "content",
            [source],
            manifest(tmp_path),
            destination_root=destination_root,
        )

    assert not (outside / "content/escape.txt").exists()


def test_staging_rejects_a_junction_destination_root(
    staging, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    write(source / "escape.txt", "escape")
    destination_root = tmp_path / "build/bin"
    original_is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == destination_root or original_is_junction(path),
    )

    with pytest.raises(staging.StagingError, match="Cannot use staging destination root"):
        staging.stage_directories(
            destination_root / "content",
            [source],
            manifest(tmp_path),
            destination_root=destination_root,
        )

    assert not destination_root.exists()


def test_files_the_module_never_staged_are_left_alone(staging, tmp_path: Path) -> None:
    """A module only knows what it staged itself, so anything else in the destination -
    another module's file, or something left there by hand - is not its to remove."""
    source = tmp_path / "source"
    write(source / "a.frag", "a")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))
    write(destination / "left_by_hand.txt", "hand written")

    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert staged_files(destination) == {"a.frag", "left_by_hand.txt"}
    assert (copied, removed) == (0, 0)


def test_manifest_records_what_was_staged(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "shaders/a.frag", "a")
    write(source / "b.txt", "b")
    destination = tmp_path / "out"
    manifest_path = manifest(tmp_path)

    staging.stage_directories(destination, [source], manifest_path)

    assert manifest_path.read_text(encoding="utf-8").split() == ["b.txt", "shaders/a.frag"]


def test_staging_recovers_when_the_destination_was_wiped(staging, tmp_path: Path) -> None:
    """The manifest still lists the files, but they are gone: they must come back rather
    than be treated as already staged."""
    source = tmp_path / "source"
    write(source / "a.frag", "a")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))

    shutil.rmtree(destination)
    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert staged_files(destination) == {"a.frag"}
    assert (copied, removed) == (1, 0)


def test_directories_left_empty_are_removed(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "nested/deep/a.frag", "a")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))

    (source / "nested/deep/a.frag").unlink()
    staging.stage_directories(destination, [source], manifest(tmp_path))

    assert not (destination / "nested").exists()


def test_two_sources_claiming_the_same_path_is_an_error(staging, tmp_path: Path) -> None:
    """They would both be copied to the same place and the winner would depend on the
    order the directories happen to be listed in."""
    first = tmp_path / "first"
    write(first / "shaders/a.frag", "first")
    second = tmp_path / "second"
    write(second / "shaders/a.frag", "second")
    destination = tmp_path / "out"

    with pytest.raises(staging.StagingError, match="provided by two sources"):
        staging.stage_directories(destination, [first, second], manifest(tmp_path))


def test_two_modules_claiming_the_same_path_is_an_error(staging, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write(first / "shared.txt", "first")
    write(second / "shared.txt", "second")
    destination = tmp_path / "out" / "content"
    plan = active_manifest_plan(
        tmp_path,
        {"content/first.manifest": [first], "content/second.manifest": [second]},
    )
    first_manifest = plan.parent / "content/first.manifest"
    second_manifest = plan.parent / "content/second.manifest"
    staging.stage_directories(destination, [first], first_manifest, plan)

    with pytest.raises(staging.StagingError, match="already staged by another module"):
        staging.stage_directories(destination, [second], second_manifest, plan)

    assert (destination / "shared.txt").read_text(encoding="utf-8") == "first"
    assert not second_manifest.exists()


def test_concurrent_modules_cannot_claim_the_same_path(staging, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write(first / "shared.txt", "first")
    write(second / "shared.txt", "second")
    destination = tmp_path / "out" / "content"
    plan = active_manifest_plan(
        tmp_path,
        {"content/first.manifest": [first], "content/second.manifest": [second]},
    )
    manifests = [plan.parent / "content/first.manifest", plan.parent / "content/second.manifest"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(staging.stage_directories, destination, [first], manifests[0], plan),
            executor.submit(staging.stage_directories, destination, [second], manifests[1], plan),
        ]

    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except staging.StagingError:
            outcomes.append(None)

    assert outcomes.count(None) == 1
    assert sum(path.exists() for path in manifests) == 1
    assert (destination / "shared.txt").read_text(encoding="utf-8") in {"first", "second"}


def test_missing_source_directory_is_an_error(staging, tmp_path: Path) -> None:
    with pytest.raises(staging.StagingError, match="does not exist"):
        staging.stage_directories(tmp_path / "out", [tmp_path / "missing"], manifest(tmp_path))


def test_staged_file_newer_than_its_source_is_restored(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "a.frag", "from source")
    destination = tmp_path / "out"
    stage_current_project(staging, tmp_path, destination, [source])

    write(destination / "a.frag", "edited in place")
    make_older(source / "a.frag")
    copied, removed = stage_current_project(staging, tmp_path, destination, [source])

    assert (destination / "a.frag").read_text(encoding="utf-8") == "from source"
    assert (copied, removed) == (1, 0)


def test_changed_source_with_the_same_timestamp_is_restaged(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "a.frag", "first")
    destination = tmp_path / "out"
    stage_current_project(staging, tmp_path, destination, [source])
    original_timestamp = source_file.stat().st_mtime_ns

    write(source_file, "other")
    os.utime(source_file, ns=(original_timestamp, original_timestamp))
    copied, removed = stage_current_project(staging, tmp_path, destination, [source])

    assert (destination / "a.frag").read_text(encoding="utf-8") == "other"
    assert (copied, removed) == (1, 0)


def test_changed_source_permissions_are_restaged(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "tool", "contents")
    destination = tmp_path / "out"
    stage_current_project(staging, tmp_path, destination, [source])
    changed_mode = stat.S_IMODE(source_file.stat().st_mode) ^ stat.S_IXUSR
    source_file.chmod(changed_mode)

    copied, removed = stage_current_project(staging, tmp_path, destination, [source])

    assert stat.S_IMODE((destination / "tool").stat().st_mode) == changed_mode
    assert (copied, removed) == (1, 0)


def test_staged_symlink_is_replaced_without_touching_its_target(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "a.frag", "from source")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))
    outside = write(tmp_path / "outside.frag", "from source")
    staged = destination / "a.frag"
    staged.unlink()
    staged.symlink_to(outside)

    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert not staged.is_symlink()
    assert staged.read_text(encoding="utf-8") == "from source"
    assert outside.read_text(encoding="utf-8") == "from source"
    assert (copied, removed) == (1, 0)


def test_removed_source_prunes_a_dangling_staged_symlink(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "a.frag", "from source")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))
    staged = destination / "a.frag"
    staged.unlink()
    staged.symlink_to(tmp_path / "missing")
    source_file.unlink()

    copied, removed = staging.stage_directories(destination, [source], manifest(tmp_path))

    assert not staged.is_symlink()
    assert (copied, removed) == (0, 1)


def test_staging_rejects_a_symlinked_parent(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "nested/a.frag", "from source")
    destination = tmp_path / "out"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (destination / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(staging.StagingError, match="Cannot use non-directory staged path"):
        staging.stage_directories(destination, [source], manifest(tmp_path))

    assert not (outside / "a.frag").exists()


def test_staging_rejects_a_symlinked_destination(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "a.frag", "from source")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "out"
    destination.symlink_to(outside, target_is_directory=True)

    with pytest.raises(staging.StagingError, match="Cannot use non-directory staging destination"):
        staging.stage_directories(destination, [source], manifest(tmp_path))

    assert not (outside / "a.frag").exists()


def test_stale_file_removal_rejects_a_symlinked_parent(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "nested/a.frag", "from source")
    destination = tmp_path / "out"
    staging.stage_directories(destination, [source], manifest(tmp_path))
    source_file.unlink()
    shutil.rmtree(destination / "nested")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = write(outside / "a.frag", "must remain")
    (destination / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(staging.StagingError, match="Cannot use non-directory staged path"):
        staging.stage_directories(destination, [source], manifest(tmp_path))

    assert outside_file.read_text(encoding="utf-8") == "must remain"


def test_staging_rejects_a_directory_at_a_file_path(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    write(source / "a.frag", "from source")
    destination = tmp_path / "out"
    (destination / "a.frag").mkdir(parents=True)

    with pytest.raises(staging.StagingError, match="Cannot replace non-file staged path"):
        staging.stage_directories(destination, [source], manifest(tmp_path))


def test_stale_file_removal_rejects_a_parent_path(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "out"
    destination.mkdir()
    outside = write(tmp_path / "outside.frag", "must remain")
    manifest_path = manifest(tmp_path)
    manifest_path.parent.mkdir()
    manifest_path.write_text("../outside.frag\n", encoding="utf-8")

    with pytest.raises(staging.StagingError, match="Invalid staged relative path"):
        staging.stage_directories(destination, [source], manifest_path)

    assert outside.read_text(encoding="utf-8") == "must remain"


def test_stale_file_removal_rejects_a_directory(staging, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = write(source / "a.frag", "from source")
    destination = tmp_path / "out"
    manifest_path = manifest(tmp_path)
    staging.stage_directories(destination, [source], manifest_path)
    source_file.unlink()
    (destination / "a.frag").unlink()
    (destination / "a.frag").mkdir()

    with pytest.raises(staging.StagingError, match="Cannot remove non-file staged path"):
        staging.stage_directories(destination, [source], manifest_path)


def test_modules_stage_to_one_destination_serially(staging, tmp_path: Path, monkeypatch) -> None:
    source_a = tmp_path / "source_a"
    source_b = tmp_path / "source_b"
    write(source_a / "nested/a.txt", "a")
    write(source_b / "nested/b.txt", "b")
    destination = tmp_path / "out"
    original_copy = staging.shutil.copy2
    counter_lock = threading.Lock()
    active_copies = 0
    maximum_active_copies = 0

    def observed_copy(source: Path, target: Path) -> None:
        nonlocal active_copies, maximum_active_copies
        with counter_lock:
            active_copies += 1
            maximum_active_copies = max(maximum_active_copies, active_copies)
        time.sleep(0.02)
        original_copy(source, target)
        with counter_lock:
            active_copies -= 1

    monkeypatch.setattr(staging.shutil, "copy2", observed_copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(staging.stage_directories, destination, [source_a], tmp_path / "a.manifest")
        second = executor.submit(staging.stage_directories, destination, [source_b], tmp_path / "b.manifest")
        assert first.result(timeout=5) == (1, 0)
        assert second.result(timeout=5) == (1, 0)

    assert maximum_active_copies == 1
    assert (destination / "nested/a.txt").read_text(encoding="utf-8") == "a"
    assert (destination / "nested/b.txt").read_text(encoding="utf-8") == "b"


def test_interrupted_manifest_replacement_preserves_the_previous_manifest(
    staging, tmp_path: Path, monkeypatch
) -> None:
    manifest_path = manifest(tmp_path)
    write(manifest_path, "previous.txt\n")

    def interrupt_replace(source: Path, destination: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(staging.os, "replace", interrupt_replace)
    with pytest.raises(KeyboardInterrupt):
        staging.write_manifest(manifest_path, {Path("replacement.txt")})

    assert manifest_path.read_text(encoding="utf-8") == "previous.txt\n"
    assert list(manifest_path.parent.glob(f".{manifest_path.name}.*")) == []
