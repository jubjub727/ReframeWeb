# Agent Workspace Implementation Design

**Status:** Implemented vertical slice with remaining hardening guidance

**Depends on:** [Agent Workspace Architecture Decisions](agent-workspace-decisions.md)

This document records the implemented vertical slice and the remaining
production-hardening path. Filesystem correctness is independent from future
agent judgment and can be tested without an LLM.

## Target Runtime Shape

```text
Python Agent Host
  generated BAML SDK
  workspace lifecycle coordinator
  IPC client
            |
            | user-local framed protocol
            v
Rust workspace daemon
  protocol server
  policy validator and path router
  workspace metadata and journal
  content-addressed store and chunk cache
  platform mount adapter
            |
            v
  ordinary workspace path used by Codex/OpenCode
```

The Agent Host starts or connects to the daemon, resolves explicit filesystem
memories through Python, mounts the resident VFS, and launches the requested
child with the mount as its working directory. Manual checkpoint selections
are typed by deterministic BAML helpers; no LLM function is present.

## Implemented Source Layout

The current vertical slice keeps one deployable crate split into small modules:

```text
workspace-fs/
  crates/
    workspace-daemon/
      daemon/              lifecycle, operations, IPC, idempotency
      resident/            provider-owned bytes, directories, mutations
      session/             state, scans, journal, checkpoints
      windows_vfs/         ProjFS callbacks and reconciliation
      unix_vfs/            Linux/macOS FUSE callbacks and scratch routing
```

The Python side should add small workspace modules under
`agent-host/src/reframe_agent_host/` and a dedicated BAML namespace under
`agent-host/baml_src/`. Generated SDK output continues to live under
`agent-host/src/baml_sdk/`.

## Core Domain Model

The platform-neutral model needs at least:

```text
WorkspaceId
NormalizedPath
WorkspaceEntry
  kind                 file, directory, symlink
  source               memory ref, blob ref, overlay, scratch
  materialization      lazy, prefetched, cached, direct disk
  retention            discard, cache-only, checkpoint, always
  metadata             size, mode, timestamps, version

WorkspaceManifest
  parent manifest
  entries
  creation metadata

JournalEvent
  create, write, rename, delete, metadata change

PolicyRule
  normalized glob
  materialization action
  retention action
  precedence and provenance
```

All internal paths use `/`, reject traversal, and are relative to the workspace
root. Platform adapters perform boundary conversion. Path comparison behavior
must be explicit rather than inherited accidentally from the host OS.

## Control Protocol

Requests and responses use the repository's single internal protocol without a
redundant public version field. Commands include:

- `Hello` and `Health`
- `CreateWorkspace`
- `ApplyPolicy`
- `MountWorkspace`
- `Prefetch`
- `GetChangeJournal`
- `ReadFileSummary`
- `CommitCheckpoint`
- `UnmountWorkspace`
- `DestroyEphemeralWorkspace`

Use length-prefixed JSON over a Windows named pipe or Linux/macOS Unix-domain
socket. Define DTOs in Rust with `serde` and mirror them with hand-written
Pydantic models in Python. Do not serialize generated BAML models directly onto
the wire.

The daemon should return structured errors containing a stable code, operation,
workspace ID, and safe diagnostic text. Requests that mutate state carry an
idempotency key so Python can safely retry after a lost response.

The implemented transport includes:

- User-only endpoint permissions and remote-client rejection.
- Request IDs and durable idempotency keys for mutations.
- Request-scoped connections so long-running children do not block IPC.
- Graceful acknowledged shutdown and stale-endpoint replacement.

## Workspace Lifecycle

### Creation and Mount

1. Python retrieves relevant memory metadata and the previous retained
   manifest, if one exists.
2. Explicit manual policy input returns a typed generated-SDK model.
3. Python translates it to protocol DTOs.
4. Rust validates paths, globs, quotas, and rule precedence.
5. Rust creates metadata, overlay, cache, and scratch locations.
6. The platform adapter mounts the workspace and performs a health probe.
7. Python launches Codex/OpenCode with the mounted path as its working
   directory and redirects temporary/package-manager caches appropriately.

### Reads and Writes

1. Directory lookup resolves the path through the compiled policy router.
2. Projected content resolves to a memory or blob reference.
3. Reads resolve an immutable buffer from the resident content map.
4. Writes replace or resize resident buffers and never create a durable copy.
5. Resident mutations update compact journal records.
6. Scratch paths bypass the overlay and journal and go directly to native disk.

No step invokes Python or BAML.

### Checkpoint and Unmount

1. Python requests the compact change journal and bounded file summaries.
2. Explicit manual checkpoint input returns typed candidate paths.
3. Rust revalidates candidates against hard rules and current filesystem state.
4. Rust writes chunks, writes the immutable manifest, and advances the head in
   one durable commit sequence.
5. The daemon unmounts and removes the OS-visible projection; resident session
   state remains available to later CLI calls.
6. Closing or destroying the session drops uncheckpointed resident bytes and
   its direct-disk scratch tree.

## Delivery Phases

### Phase 0: Feasibility Spikes

Build tiny disposable adapter probes before committing the core to an OS model:

- Project one static file and one directory.
- Read, write, rename, delete, lock, memory-map, and watch files.
- Confirm clean and forced unmount behavior.
- Measure a dependency-heavy tree on native disk versus the adapter.

Run the probes for Linux FUSE, Windows ProjFS, and the intended macOS backend.
Record unsupported semantics and choose explicit compatibility behavior.

### Phase 1: Platform-Neutral Core

- Implement normalized paths, manifests, policy compilation, and precedence.
- Implement an in-memory metadata/blob backend for deterministic tests.
- Implement overlay copy-on-write and journal semantics without mounting.
- Add property tests for rename, delete, tombstones, and path containment.

Exit criterion: the same operation trace always produces the same manifest and
journal on every OS.

### Phase 2: Persistence and Cache

- Add SQLite schema migrations and a single controlled writer.
- Add BLAKE3 whole-file storage first, then chunk files above a measured size.
- Add local `object_store` persistence and immutable manifest commits.
- Add the `ChunkCache` interface and foyer implementation.
- Add mark-and-sweep garbage collection from retained heads.

Exit criterion: kill the process at every checkpoint boundary and recover
without exposing a partial workspace head.

### Phase 3: First Mounted Vertical Slice

Choose one adapter after Phase 0 rather than forcing identical implementation
details. The slice must support:

- Lazy projection of a retained file.
- Copy-on-write editing.
- Creation, rename, and deletion.
- Remounting the retained checkpoint.
- A direct-disk dependency directory.

The current development host makes Windows ProjFS a practical first slice, but
the core contract must also be exercised by the platform-neutral harness so
ProjFS behavior does not become the universal model.

### Phase 4: Python and Generated BAML SDK Integration (implemented)

- Add BAML types plus deterministic `ManualWorkspacePlan` and
  `ManualCheckpoint` functions without clients or prompts.
- Run `baml generate` and expose the generated Python types.
- Add explicit translators from generated models to IPC DTOs.
- Add user-local framed-JSON daemon startup, health, mount, journal,
  checkpoint, and unmount calls.
- Pin BAML toolchain and `baml-core` versions and add a generation-diff CI check.

Exit criterion: an Agent Host integration test can mount, run a scripted child
process, checkpoint one selected output, discard another, and remount.

### Phase 5: Scratch Redirections (implemented)

- Compile built-in redirect rules through `globset`.
- Route scratch operations to per-session native-disk trees on every adapter.
- Route package-manager caches and temporary directories outside retained data.
- Enforce that redirected paths cannot be checkpointed.

Exit criterion: installing dependencies creates a usable `node_modules` tree,
does not add it to the journal, and leaves no retained chunks after teardown.

### Phase 6: Remaining Platform Adapters (implemented; native validation ongoing)

Linux, Windows, and macOS adapters share the same resident core. Continued
native conformance work should cover:

- Windows must reconcile ProjFS full files, tombstones, and offline changes.
- Linux must manage mount cleanup, invalidation, and bind redirects.
- macOS must validate packaging, Unicode normalization, watchers, and the chosen
  FUSE/FSKit path.

### Phase 7: Hardening

- Add optional per-launch authentication if the user-local OS boundary proves insufficient.
- Add quotas for RAM cache, disk cache, overlay, scratch, and retained writes.
- Add cancellation, backpressure, metrics, and structured tracing.
- Add startup recovery, orphan mount detection, and administrative cleanup.
- Fuzz protocol decoding, normalized paths, manifests, and journal replay.

## Test Matrix

### Deterministic Tests

- Path normalization, traversal rejection, case collisions, and Unicode names.
- Rule precedence and rejection of invalid BAML output.
- CAS deduplication, chunk range reads, and cache eviction safety.
- Manifest transactions, garbage collection, and journal replay.
- Generated-model to IPC-DTO translation.

### Filesystem Conformance

- Random and sequential reads and writes.
- Open-file rename/delete behavior.
- Symlinks or the documented platform substitute.
- File locks, executable bits, timestamps, and memory mapping.
- File watcher delivery and invalidation.
- Abrupt daemon, Agent Host, and machine termination.

### Agent Acceptance Scenarios

1. A memory-derived source file appears without eager hydration.
2. Codex/OpenCode edits it using ordinary tools.
3. A package manager creates dependencies on direct disk.
4. BAML selects one output to retain and rejects generated noise.
5. The workspace unmounts, discards dependencies, and remounts the retained
   output correctly.

## Initial Success Criteria

The first usable release is complete when:

- Agents require no custom filesystem-aware tools.
- No filesystem callback depends on Python, BAML, or network availability.
- Dependency/build trees can bypass the userspace overlay.
- Retention is typed, validated, atomic, and defaults to discard.
- Cache eviction cannot affect retained data.
- Crash recovery never advances a workspace to a partial checkpoint.
- The same acceptance scenarios pass on supported Windows, Linux, and macOS
  versions.
