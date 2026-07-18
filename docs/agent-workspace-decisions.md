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
- A resident RAM tier plus explicit direct-disk scratch and persistent storage.
- Typed manual policy surfaces that future agent logic can drive when requested.
- Consistent operation on Linux, macOS, and Windows.

Codex, OpenCode, shells, compilers, package managers, and other child processes
must not require custom file tools. They should receive a normal working
directory and use normal operating-system filesystem calls.

## Decision Summary

ReframeWeb will implement an EdenFS-shaped projected workspace. A long-lived
Rust filesystem daemon will expose a mounted directory and route paths between
resident projected content, direct-disk scratch redirections, and retained
content-addressed snapshots.

The Python Agent Host owns workspace orchestration, graph-memory access, and
translation of typed policy values. The Agent Host communicates with the Rust
daemon through the repository's single internal local IPC protocol. BAML and
Python never participate in individual filesystem operations.

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
| Memory-derived input | Hash-deduplicated resident bytes | Keep its source reference |
| Ordinary agent edits | Resident writable VFS | Discard unless selected |
| Selected deliverable | Resident bytes followed by checkpoint | Keep an immutable snapshot |
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
- **BLAKE3 content addressing** for retained file data and deduplication in the
  resident store. Whole-file objects remain the measured starting point.
- **Provider-owned resident buffers** for every ordinary active-workspace file.
  Source and checkpoint objects are read and verified before mount; callbacks
  never reopen their backing files.
- **`globset`** for compiled path rules with explicit separator,
  case-sensitivity, and normalization behavior.

The resident store and persistent content-addressed store are separate. An
uncheckpointed file has no durable content copy. Windows uses temporary-file
cache semantics and removes dirty/full ProjFS items after absorbing writes;
Linux and macOS FUSE callbacks read and write resident buffers directly.

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

BAML can carry typed decisions at workspace lifecycle boundaries, never on the
filesystem hot path. The implemented non-LLM BAML surfaces are:

- `ManualWorkspacePlan`: validate explicit memory and prefetch selections.
- `ManualCheckpoint`: validate explicit paths chosen for retention.

They contain no client, prompt, or model call. Any future LLM policy function
requires a separate direct instruction and is not implied by this design.

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

Generated BAML models are not IPC models. Python converts them into small
protocol DTOs before sending policy to Rust.

Policy precedence is deterministic:

1. User-pinned rules.
2. Platform and safety constraints.
3. Built-in scratch and retention rules.
4. Validated BAML decisions.
5. Default to discard.

## Local IPC

Python controls the daemon through the repository's local protocol containing
operations such as mount, apply policy, prefetch, read journal, checkpoint,
unmount, and health. Four-byte length-prefixed JSON travels over a user-local
Unix-domain socket on Linux/macOS or native named pipe on Windows. Each
connection carries one request and response so a task shell cannot monopolize
the daemon. Unix endpoints are mode `0600`; Windows rejects remote clients.

## Checkpoint Atomicity

A checkpoint is committed in this order:

1. Hash and write every selected content chunk.
2. Write an immutable workspace manifest referencing those chunks.
3. Atomically advance the workspace head in SQLite.
4. Only then discard ephemeral state.

Garbage collection is mark-and-sweep from retained manifest roots. Any future
agent-selected retention candidates cannot directly delete persistent chunks
or bypass transaction rules.

## Consequences and Open Questions

This design preserves ordinary filesystem transparency and gives each storage
tier a clear lifecycle. It also requires serious cross-platform conformance and
crash-recovery work. Case folding, Unicode normalization, symlinks, locks,
memory mapping, file watchers, and open-file renames cannot be assumed to behave
identically across adapters.

The following remain implementation-time decisions:

- The macOS support floor and whether a native FSKit shim is required at launch.
- Exact chunk size and cache admission/eviction policy after benchmarks.
- Whether a remote object store is required for the first release.
