# YAE Support

Shared support package for YAE-generated CMake projects.

This repository contains:

- `cmake/`: CMake utility modules used by generated projects.
- `modules/third_party/`: common third-party module declarations.
- `modules/examples/`: example modules used for YAE validation and demos.

YAE injects this package as an implicit dependency so generated CMake projects do not need a `YAE_ROOT` path.
