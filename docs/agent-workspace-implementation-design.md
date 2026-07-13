# Agent Workspace Implementation Design

**Status:** Proposed implementation sequence

**Depends on:** [Agent Workspace Architecture Decisions](agent-workspace-decisions.md)

This document describes a rough path from the accepted workspace architecture
to a production implementation. It intentionally separates filesystem
correctness from BAML judgment so each can be tested without the other.

## Target Runtime Shape

```text
Python Agent Host
  generated BAML SDK
  workspace lifecycle coordinator
  IPC client
            |
            | versioned local protocol
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

The Agent Host starts or connects to the daemon, asks BAML to plan the
workspace, mounts it, launches the agent with the mount as its working
directory, and later asks BAML to choose a checkpoint from the daemon's journal.

## Proposed Source Layout

Keep crates and modules small and named by intent. A likely Rust workspace is:

```text
workspace-fs/
  crates/
    workspace-model/       paths, entries, manifests, policy types
    workspace-store/       SQLite metadata, CAS, object_store backend
    workspace-cache/       ChunkCache trait and foyer adapter
    workspace-protocol/    versioned request and response DTOs
    workspace-daemon/      lifecycle, IPC, recovery, orchestration
    workspace-linux/       fuser adapter and redirect mounts
    workspace-windows/     ProjFS adapter and reconciliation
    workspace-macos/       FUSE/FSKit-facing adapter
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

Start with a protocol version in every request and response. Initial commands:

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

Use length-prefixed JSON over stdio for the first vertical slice. Define the
DTOs in Rust with `serde` and mirror them with hand-written Pydantic models in
Python. Do not serialize generated BAML models directly onto the wire.

The daemon should return structured errors containing a stable code, operation,
workspace ID, and safe diagnostic text. Requests that mutate state carry an
idempotency key so Python can safely retry after a lost response.

Before moving to local sockets, add:

- User-only endpoint permissions.
- A random session token inherited from the Agent Host.
- Connection and request timeouts.
- Graceful shutdown and stale-daemon detection.

## Workspace Lifecycle

### Creation and Mount

1. Python retrieves relevant memory metadata and the previous retained
   manifest, if one exists.
2. `PlanWorkspace` returns a typed generated-SDK model.
3. Python translates it to protocol DTOs.
4. Rust validates paths, globs, quotas, and rule precedence.
5. Rust creates metadata, overlay, cache, and scratch locations.
6. The platform adapter mounts the workspace and performs a health probe.
7. Python launches Codex/OpenCode with the mounted path as its working
   directory and redirects temporary/package-manager caches appropriately.

### Reads and Writes

1. Directory lookup resolves the path through the compiled policy router.
2. Projected content resolves to a memory or blob reference.
3. Reads check the OS cache, then the chunk cache, then persistent storage.
4. The first write materializes projected content into the writable overlay.
5. Overlay mutations append compact journal records.
6. Scratch paths bypass the overlay and journal and go directly to native disk.

No step invokes Python or BAML.

### Checkpoint and Unmount

1. Python requests the compact change journal and bounded file summaries.
2. `ChooseCheckpoint` returns candidate paths and reasons.
3. Rust revalidates candidates against hard rules and current filesystem state.
4. Rust writes chunks, writes the immutable manifest, and advances the head in
   one durable commit sequence.
5. The daemon unmounts and removes overlay and scratch data.
6. Cache entries remain subject only to normal cache quotas.

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

### Phase 4: Python and Generated BAML SDK Integration

- Add BAML types and `PlanWorkspace`/`ChooseCheckpoint` functions.
- Run `baml generate` and import the generated async Python functions.
- Add explicit translators from generated models to IPC DTOs.
- Add framed-JSON daemon startup, health, mount, journal, checkpoint, and
  unmount calls.
- Pin BAML toolchain and `baml-core` versions and add a generation-diff CI check.

Exit criterion: an Agent Host integration test can mount, run a scripted child
process, checkpoint one selected output, discard another, and remount.

### Phase 5: Scratch Redirections

- Compile built-in and BAML-suggested redirect rules through `globset`.
- Implement Linux bind mounts and platform-appropriate Windows/macOS behavior.
- Route package-manager caches and temporary directories outside retained data.
- Enforce that redirected paths cannot be checkpointed.

Exit criterion: installing dependencies creates a usable `node_modules` tree,
does not add it to the journal, and leaves no retained chunks after teardown.

### Phase 6: Remaining Platform Adapters

Add Linux, Windows, and macOS adapters against the same conformance harness.
Adapter-specific reconciliation is expected:

- Windows must reconcile ProjFS full files, tombstones, and offline changes.
- Linux must manage mount cleanup, invalidation, and bind redirects.
- macOS must validate packaging, Unicode normalization, watchers, and the chosen
  FUSE/FSKit path.

### Phase 7: Hardening

- Move IPC from stdio to authenticated local sockets/named pipes if needed.
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
