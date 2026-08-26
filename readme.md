# YAE Support

Shared support package for YAE-generated CMake projects.

This repository contains:

- `cmake/`: CMake utility modules used by generated projects.
- `scripts/`: scripts run by generated projects at build time.
- `tests/`: unit tests for the build-time scripts.
- `modules/third_party/`: common third-party module declarations.
- `modules/examples/`: example modules used for YAE validation and demos.

YAE injects this package as an implicit dependency so generated CMake projects do not need a `YAE_ROOT` path.

Everything here is used by generated projects while they build, and those projects must build without
YAE installed — so this package cannot depend on it. `scripts/` needs Python 3.12 or newer, which
generated projects find with `find_package(Python3 3.12)`.

The scripts have unit tests in this repository. CI also runs YAE's integration suite against this
checkout so changes to the generated-project interface are visible before the repositories land.

Run the unit tests with:

```sh
uv run --python 3.12 --with pytest pytest
```

## Scripts

| Script | Used by |
| --- | --- |
| `stage_directories.py` | The `<target>_copy_files` target generated for a module that declares `CopyDirectoriesAfterBuild`. Stages that module's directories next to the built binary, and removes what it staged before whose source is gone. |
