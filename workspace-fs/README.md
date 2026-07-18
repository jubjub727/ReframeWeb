# Reframe Agent Workspace backing service

This directory contains the internal Rust filesystem service used by the
uv-managed Agent Host. It is not a separate user-facing application.

`agent-host` declares a version-matched `reframe-workspace-daemon` companion
distribution. During development,
uv resolves that dependency from this directory and maturin installs the Rust
executable into the same virtual environment as `reframe-agent-host`. The Agent
Host wheel does not embed the daemon or a checkout-relative path: a release must
publish the companion platform wheel alongside the Agent Host wheel. Packaging
CI resolves the published dependency graph, builds and installs both
distributions together, then exercises the generated BAML runtime and daemon
lookup. Python connects to one persistent per-user daemon over the local framed
IPC boundary described below.

The Agent Host also records its BAML bridge as an exact PEP 508 Git reference,
including the commit and repository subdirectory, so ordinary installation may
need Git plus a Rust build toolchain. The intended release channel must permit
direct references. Moving to a registry-only channel requires publishing that
exact bridge build first and replacing the direct reference deliberately.

The mounted filesystem never calls Python, BAML, an LLM, or the network.
Python owns memory graph access, policy orchestration, child-process launching,
and lifecycle I/O. Rust owns the resident VFS, platform mount callbacks, path
routing, workspace metadata, journaling, retained content, and checkpoints.

## Setup

Install the existing Agent Host normally:

```powershell
cd agent-host
uv sync
```

There is no separate workspace CLI to install or invoke.

The platform mount prerequisite is Windows **Projected File System**, Linux
FUSE (`/dev/fuse` plus normal user mount permission), or macFUSE 4 on macOS.
Windows uses ProjFS, while Linux and macOS use the same Rust FUSE adapter.

Create a real native shortcut to the shared sessions directory in the cloned
repository with:

```powershell
uv run reframe-agent-host workspace session shortcut
```

The command generates a Windows shell link or a macOS/Linux directory link on
the machine running it. No machine-specific target is committed to Git.

## Filesystem memories

Filesystem memories are ordinary `memory_node` records under the
`memory_root:filesystem_memories` root in the existing SurrealDB memory graph.
The node stores descriptive metadata and the discovered project root. File
contents remain real files and may be edited manually between sessions. No path
is accepted by the testing CLI: it walks upward from the current directory to
the Git root and registers that project idempotently.

```powershell
uv run reframe-agent-host workspace memory create
uv run reframe-agent-host workspace memory list
```

The returned `memory_node:...` ID is the identity used by workspace plans and
manual task sessions. Python resolves that node through `reframe_memory`, marks
it read, validates the source directory, and translates it into a small IPC DTO.
Rust does not search or reproduce graph-memory behavior.

## Manual task sessions

```powershell
uv run reframe-agent-host workspace session create
uv run reframe-agent-host workspace session shell
```

Creation generates the name and session ID, locates the shared workspace store
in the platform application-data directory, and applies the built-in scratch
policy. With no options, the projected workspace starts empty. Files enter it
only through session writes, explicit `--memory memory_node:...` selections, or
`--continue` from a checkpoint memory. `memory create` explicitly registers the
current project when testing directory-memory projection.

The shell's current directory is the native mounted workspace. Selected source
and checkpoint bytes are hash-validated, deduplicated, and loaded into RAM
before the mount becomes available. Reads are served from that resident store.
Writes, creations, truncations, renames, empty directories, and deletions update
the same store and its journal.

On Windows, projected files carry `FILE_ATTRIBUTE_TEMPORARY`; after a writable
handle closes, the provider absorbs its bytes and removes the dirty/full ProjFS
item. On Linux and macOS, FUSE reads and writes the resident buffers directly.
After unmount the worktree is empty, while the long-lived daemon keeps volatile
session bytes available for later CLI commands. Only checkpointing writes those
bytes to the persistent content store.

Built-in direct-disk scratch roots cover source-control metadata, uv/Python
environments and caches, workspace internals, dependency trees, and common
build outputs. Rules are compiled with separator-aware, platform-case-aware
`globset` matching and enforced during projection, callbacks, reconciliation,
and checkpoint validation. Scratch content cannot enter a journal or
checkpoint. The testing CLI does not expose this internal policy.

```powershell
uv run reframe-agent-host workspace session status
uv run reframe-agent-host workspace session checkpoint --include src\answer.rs
uv run reframe-agent-host workspace session create --continue
```

Checkpointing is discard-by-default and requires `--include` or `--all`. After
the daemon durably commits the immutable manifest and content-addressed blobs,
Python publishes a real filesystem-memory node in the graph. The node references
the shared backing store and manifest plus its base memories; it does not own or
duplicate those stored objects. Any number of memory nodes can reference the
same persistent manifest. `--continue` resolves the published checkpoint memory
through the normal Python memory surface and projects it like any other memory.
Manifest commit and a SQLite publication-outbox row share one transaction, so a
host or graph-database failure cannot lose a committed checkpoint; the Agent
Host reconciles pending rows idempotently on a later invocation.

Commands can run non-interactively through the same mounted lifecycle:

```powershell
uv run reframe-agent-host workspace session exec -- cargo test
```

Session lifecycle commands select the latest session automatically. The
advanced `--session ID` override exists only for inspecting or branching older
test sessions.

## IPC boundary

The installed daemon serves four-byte little-endian length-prefixed JSON over a
user-local named pipe on Windows and a Unix-domain socket on Linux/macOS. Every
request and response carries a request ID. Connections carry one request and
close after its response, so a long-lived task shell never monopolizes IPC.
Mutating requests require idempotency keys. Durable workspace mutations persist
their responses in SQLite for replay, while process-local lifecycle operations
such as mount, prefetch, unmount, and shutdown re-evaluate the current daemon
state after a restart. The hello handshake validates the protocol version,
frame limit, capabilities, and operation idempotency-scope table before normal
requests proceed. Both transports enforce bounded I/O, and an exclusive store
lock prevents two daemon processes from
owning the same endpoint and SQLite store.
Completed durable replay records and published outbox entries are retained for
30 days; pending reservations and publications remain until explicitly
reconciled so crash recovery evidence is never pruned automatically.

Implemented operations cover hello/health, create/apply-policy, mount/prefetch,
journal/status/file-summary, checkpoint, unmount, close, destroy, and shutdown.
The daemon remains alive across CLI invocations so volatile session bytes do not
need a disk surrogate. Python launches the requested child only after
`mount_workspace` succeeds and always requests unmount in a `finally` boundary.

## BAML boundary

`agent-host/baml_src/ns_workspace` contains deterministic workspace policy and
checkpoint types plus manual helper functions. They make the future policy call
surface typed without introducing an LLM function or prompt. Generated Python
models live in the existing `baml_sdk.workspace` namespace. After changing this
BAML source, run these checkout-only commands from `agent-host`:

```powershell
uv run reframe-generate-baml
uv run reframe-check-baml
```

The wrapper also normalizes embedded source paths so generated artifacts remain
portable. The check command verifies that committed output is current. These
developer commands resolve BAML sources from the current checkout rather than
assuming they were packaged into the runtime wheel.

## Storage

The workspace store contains:

- Versioned SQLite WAL metadata for resolved source references, workspaces,
  direct-disk policy, baselines, journals, immutable manifests, heads,
  idempotency, and checkpoint publication outbox state.
- Immutable BLAKE3-addressed retained blobs written before head advancement.
- Per-session mountpoints that are empty while unmounted.
- Provider-owned, hash-deduplicated RAM for active session files and empty
  directories.
- Per-session direct-disk scratch trees for explicitly discardable dependency,
  cache, VCS, and build paths.

Source and checkpoint-memory identity remain in SurrealDB. SQLite manifests and
BLAKE3 objects are shared backing-store items; they are not owned by one memory
and can be projected by every memory node that references them.
