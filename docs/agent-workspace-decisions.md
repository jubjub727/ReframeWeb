# Agent Workspace Architecture Decisions

**Status:** Accepted for implementation

**Date:** 2026-07-13

This document records the architectural decisions for giving Codex, OpenCode,
and their child processes a transparent, memory-aware workspace. The separate
[implementation design](agent-workspace-implementation-design.md) turns these
decisions into a proposed delivery sequence.

## Context

An agent workspace should look like an ordinary directory while combining:

- Files projected from persistent memories or retained workspace snapshots.
- Files created or modified during the current task.
- High-volume dependency and build trees that must use disk but must not be
  retained.
- A bounded RAM and disk cache in front of persistent storage.
- BAML judgments about what to materialize and retain.
- Consistent operation on Linux, macOS, and Windows.

Codex, OpenCode, shells, compilers, package managers, and other child processes
must not require custom file tools. They should receive a normal working
directory and use normal operating-system filesystem calls.

## Decision Summary

ReframeWeb will implement an EdenFS-shaped projected workspace. A long-lived
Rust filesystem daemon will expose a mounted directory and route paths between
lazy projected content, a writable working overlay, direct-disk scratch
redirections, and retained content-addressed snapshots.

The Python Agent Host will own workspace orchestration and BAML policy calls.
BAML will be called through the existing generated Python/Pydantic SDK. The
Agent Host will communicate with the Rust daemon through a versioned local IPC
protocol. BAML and Python will never participate in individual filesystem
operations.

## Storage Properties Are Independent

Every workspace entry has three independent properties:

1. **Source**: memory reference, retained blob, newly created content, or native
   scratch content.
2. **Materialization**: lazy, prefetched, cache-backed, or direct disk.
3. **Retention**: discard, cache-only, checkpoint, or always persist.

This avoids treating "memory-derived" as synonymous with "currently stored in
RAM." Semantic memory references and the runtime byte cache are separate
concepts and should use distinct names in code.

| Path class | Active workspace | After unmount |
| --- | --- | --- |
| Memory-derived input | Lazy projection with bounded caching | Keep its source reference |
| Ordinary agent edits | Writable disk overlay | Discard unless selected |
| Selected deliverable | Overlay followed by checkpoint | Keep an immutable snapshot |
| `node_modules`, `target`, build output | Direct native-disk redirection | Delete |
| Small transient metadata | RAM or cache | Delete |

## Filesystem Process Boundary

The mounted filesystem will be a separate Rust daemon rather than a Python
extension module.

Reasons:

- Filesystem callbacks must not wait for Python, BAML, or the Python GIL.
- Agent Host failures must not corrupt an active mount.
- Mount lifecycle, service privileges, and OS-specific drivers remain isolated.
- Rust and Python can be tested, restarted, and upgraded independently.

PyO3 remains suitable for other Rust libraries, but it is not the process
boundary for the workspace filesystem.

## Platform Adapters

The storage model and policy engine will live behind a platform-neutral Rust
interface. OS callbacks must be translated at the edge instead of leaking FUSE
or ProjFS concepts into the storage core.

- **Linux:** FUSE through [`fuser`](https://docs.rs/fuser/latest/fuser/).
  Native bind mounts should implement direct-disk redirections when possible.
- **Windows:** native Projected File System through `windows-rs` and its
  [ProjectedFileSystem bindings](https://microsoft.github.io/windows-docs-rs/doc/windows/Win32/Storage/ProjectedFileSystem/index.html).
  ProjFS already models virtual, placeholder, hydrated, dirty, full, and
  tombstoned entries.
- **macOS:** begin with a replaceable FUSE adapter using macFUSE `libfuse3`.
  Validate its userspace FSKit backend on macOS 15.4 and later. A thin native
  FSKit extension calling the Rust core remains the preferred long-term option
  if packaging or compatibility requires it.

[`unifuse`](https://docs.rs/unifuse/latest/unifuse/) may inform adapter design or
support a prototype, but it is not the production foundation. WinFsp and Dokany
remain Windows fallbacks if ProjFS limitations become blocking. WinFsp licensing
must be reviewed before adoption.

## Persistent Storage and Caching

The initial storage stack is:

- **SQLite through `rusqlite`** for workspace metadata, immutable manifests,
  workspace heads, memory references, tombstones, and the change journal. Use
  WAL mode and a controlled writer boundary.
- **BLAKE3 content addressing** for retained file data. Large files are split
  into fixed-size chunks, initially targeting 1-4 MiB pending benchmarks.
- **`object_store`** behind the blob persistence interface so local storage and
  remote object storage can share the same core.
- **`foyer`** behind a project-owned `ChunkCache` trait for bounded RAM and disk
  caching. It must remain replaceable because it is still evolving.
- **`globset`** for compiled path rules with explicit separator,
  case-sensitivity, and normalization behavior.

The cache and persistent content-addressed store must use separate locations.
Cache eviction must never delete retained data. Kernel page caching and Windows
placeholder hydration should be used before adding duplicate userspace copies.

## Direct-Disk Redirections

High-write generated trees bypass the userspace overlay and write directly to a
workspace-specific scratch directory. Default redirections include:

- `**/node_modules/**`
- `**/target/**`
- Common build and package-manager output directories
- Explicit task-specific scratch paths

Redirected paths are never checkpoint candidates. If an output may need to be
retained, it must be written outside a scratch redirect. This follows the
[EdenFS redirection model](https://github.com/facebook/sapling/blob/main/eden/fs/docs/Redirections.md).

## BAML Policy Boundary

BAML makes typed decisions at workspace lifecycle boundaries, not on the
filesystem hot path. The initial BAML surfaces are:

- `PlanWorkspace`: choose projected memories, prefetch candidates, and policy
  rules before the agent starts.
- `ChooseCheckpoint`: choose which changed files should survive after the task.

The existing generator in `agent-host/baml.toml` remains authoritative:

```toml
[generator.target]
output_type = "python/pydantic"
output_dir = "src"
naming_convention = "preserve-case"
```

The generated SDK is imported by the long-lived Python Agent Host. Runtime use
of `baml run` is explicitly not part of this design. The BAML toolchain version
and Python `baml-core` dependency must remain exactly matched, generation must
run after schema changes, and CI should fail when regeneration produces a diff.

Generated BAML models are not IPC models. Python converts them into small,
versioned protocol DTOs before sending policy to Rust.

Policy precedence is deterministic:

1. User-pinned rules.
2. Platform and safety constraints.
3. Built-in scratch and retention rules.
4. Validated BAML decisions.
5. Default to discard.

## Local IPC

Python controls the daemon through a versioned local protocol containing
operations such as mount, apply policy, prefetch, read journal, checkpoint,
unmount, and health.

The first implementation may use framed JSON over child-process stdio. The
production transport should use Unix-domain sockets on Linux/macOS and named
pipes on Windows, with Rust's
[`interprocess`](https://docs.rs/interprocess/latest/interprocess/local_socket/)
as the initial abstraction. The transport remains local-only and user-scoped.

## Checkpoint Atomicity

A checkpoint is committed in this order:

1. Hash and write every selected content chunk.
2. Write an immutable workspace manifest referencing those chunks.
3. Atomically advance the workspace head in SQLite.
4. Only then discard ephemeral state.

Garbage collection is mark-and-sweep from retained manifest roots. LLM output
may select retention candidates, but it cannot directly delete persistent
chunks or bypass transaction rules.

## Consequences and Open Questions

This design preserves ordinary filesystem transparency and gives each storage
tier a clear lifecycle. It also requires serious cross-platform conformance and
crash-recovery work. Case folding, Unicode normalization, symlinks, locks,
memory mapping, file watchers, and open-file renames cannot be assumed to behave
identically across adapters.

The following remain implementation-time decisions:

- Final IPC encoding after the framed-JSON prototype.
- The macOS support floor and whether a native FSKit shim is required at launch.
- Exact chunk size and cache admission/eviction policy after benchmarks.
- Whether a remote object store is required for the first release.
