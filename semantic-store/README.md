# Reframe Semantic Store host

This workspace is the local, presentation-independent Semantic Store host
described in the [runtime design](../docs/semantic-store-design.md). It provides
the fixed protobuf protocol, strict package verification, bounded catalog
discovery, an embeddable asynchronous Wasmtime runtime, local IPC, a Store SDK,
and a small conformance CLI. It does not depend on Python, BAML, CEF, or a Visual
Panel.

The host executes WebAssembly Components, not core WebAssembly modules. Wasmtime,
WASI, and the WIT HTTP interface are pinned as one set: Wasmtime `46.0.1` and
`wasi:http@0.2.12`. The workspace's minimum Rust version is `1.94`.

## Architecture

| Crate | Owns |
| --- | --- |
| `reframe-store-protocol` | Generated fixed wire/package protobuf types, descriptor bytes, and envelope/version validation. |
| `reframe-store-package` | Bounded `.rstore` creation, exact-byte hashes, archive validation, descriptor loading, and catalog-to-schema validation. |
| `reframe-store-catalog` | Immutable lexical indexing, bounded search/browse, selective inspection, authenticated cursors, type projection, and `Any` validation. |
| `reframe-store-sdk` | Canonical WIT package, guest request decoding, typed `Any` helpers, and buffered or pull-driven event streams. |
| `reframe-store-runtime` | Session negotiation, immutable Store revisions, component compilation, WASI HTTP, isolated invocations, streaming, and cancellation routing. |
| `reframe-store-transport` | Cross-platform local endpoints and four-byte big-endian protobuf framing with bounded concurrency and backpressure. |
| `reframe-store-host` | Thin library/CLI composition of verified packages, runtime, transport, tracing, and Ctrl+C handling. |
| `reframe-reference-store` | Small typed HTTP and counter resources plus deterministic package metadata for conformance work. |

Catalog and inspection requests are answered from verified immutable metadata;
they do not enter WebAssembly. A read, call, or subscription gets a fresh
Wasmtime store and component instance. Compiled components and verified package
metadata are shared, but active execution contexts are not.

## Build and verify the workspace

Run commands from `semantic-store`:

```shell
cargo +1.94.0 build --workspace --locked
cargo +1.94.0 fmt --all -- --check
cargo +1.94.0 clippy --workspace --all-targets --locked -- -D warnings
cargo +1.94.0 test --workspace --all-targets --locked
cargo +1.94.0 package --locked -p reframe-store-sdk --list --allow-dirty
```

The Rust reference glue is built as a core module before packaging, so it needs
the target below:

```shell
rustup target add wasm32-unknown-unknown --toolchain 1.94.0
```

`package-reference-store` uses `wit-component` to componentize that module
against the canonical WIT world before creating the `.rstore`. Rust 1.94's
`wasm32-wasip2` sysroot imports WASI 0.2.6, while this host deliberately pins
WASI HTTP 0.2.12, so a direct `wasm32-wasip2` reference build is not a compatible
substitute.

The generated Canonical ABI shims are isolated in the tiny
`reference-store/component` crate. Unsafe code remains forbidden in the Store
SDK and reference application logic.

## Build and run the reference Store

The reference Store provides three resources and two functions:

- `reference.http.loopback_snapshot` performs a bounded WASI HTTP GET to
  `localhost`, an IPv4 loopback address, or an IPv6 loopback address.
- `reference.http.snapshot` performs a bounded WASI HTTP GET for an arbitrary
  absolute HTTP or HTTPS URL.
- `reference.streams.counter` supports a unary read and a deterministic bounded
  subscription with typed Data and Progress events.
- `reference.text.normalize_label` is a pure idempotent typed function.
- `reference.diagnostics.trap` intentionally traps after Started to exercise
  host fault isolation and recovery.

Build the component, create a package through the same verified builder used by
the host, verify it, and serve it:

```shell
cargo +1.94.0 build --locked -p reframe-reference-store-component --target wasm32-unknown-unknown --release
cargo +1.94.0 run --locked -p reframe-reference-store --bin package-reference-store -- target/wasm32-unknown-unknown/release/reframe_reference_store_component.wasm target/reference-store.rstore
cargo +1.94.0 run --locked -p reframe-store-host -- verify target/reference-store.rstore
cargo +1.94.0 test --locked -p reframe-store-host --test reference_conformance -- --ignored --nocapture
cargo +1.94.0 run --locked -p reframe-store-host -- serve --package target/reference-store.rstore
```

The ignored conformance test is intentionally opt-in because it consumes the
release component built by the first command. It exercises real local IPC,
Wasmtime, loopback HTTP and ordinary HTTPS, incremental subscriptions, targeted
cancellation while peer I/O remains active, guest-trap recovery, session
ownership, shutdown, and frame invariants rather than a mocked guest boundary.

`serve` logs to stderr; Ctrl+C requests shutdown. Its default service name is
`reframe-semantic-store`. Use `--service-name NAME` to run an independent host;
names are limited to 1 to 64 ASCII letters, digits, dots, underscores, and hyphens.
Repeat `--package PATH` to load multiple Store IDs. `--max-sessions` defaults to
1,024 and `--max-invocations-per-session` defaults to 128.

On Windows the default endpoint is
`\\.\pipe\reframe-semantic-store`. On Linux and macOS it is
`$XDG_RUNTIME_DIR/rfs-<uid>/s-<service-sha256>.sock` when `XDG_RUNTIME_DIR`
is a usable absolute directory. Otherwise the same private per-user directory
is created below the platform temporary directory, with a bounded `/tmp`
fallback for platforms whose Unix-socket address space is especially short.
Clients should construct the address with `LocalEndpoint::for_service` instead
of reproducing these paths.

## Author a Store package

A Store's application contract remains ordinary protobuf. The transport is not
gRPC, but catalog resource/function bindings must name real service methods in
the packaged descriptor set.

1. Define narrow application messages and services in `.proto` files. Import
   the canonical annotation proto, mark each Store-owned service with
   `store_service { store_id: "..." }`, and annotate its Resource and Function
   methods. Keep capability IDs stable and declare useful guidance, hidden
   intent phrases, side effects, and idempotency in those options.
2. Supply `AuthoredCatalog` with the same Store ID, exactly two overview
   sentences, and only Topics, Workflows, and typed Examples keyed by
   capability ID. `generate_catalog` derives every Resource/Function binding
   and input/output type from the original descriptor bytes, sorts entries by
   ID, and derives the root topic list.
3. Implement the [canonical WIT world](crates/store-sdk/wit/semantic-store.wit). In Rust,
   `reframe-store-sdk` decodes the fixed `ComponentInvocationRequest`, checks
   typed `google.protobuf.Any` values, and builds valid Started/Data/Progress/
   Complete/Failure streams.
4. Produce a WebAssembly Component implementing that world. The reference Rust
   path compiles `wit-bindgen` component glue for `wasm32-unknown-unknown`, then
   componentizes the resulting core module during packaging.
5. Create the archive with `PackageBuilder::from_annotated_schema`. Use
   `PackageBuilder::from_catalog` only for an explicitly legacy or
   already-generated catalog, or use the CLI below when the three binary
   artifacts already exist.

For example, a Rust Store build script must give protoc the application schema,
canonical annotation, and well-known-type roots. `prost-build` then emits a
descriptor set with imports and source locations:

```rust
let proto = std::path::PathBuf::from("proto/store.proto");
let out_dir = std::env::var_os("OUT_DIR").ok_or("OUT_DIR is not set")?;
let descriptor = std::path::PathBuf::from(out_dir).join("store_descriptor.bin");
let includes = [
    std::path::PathBuf::from("proto"),
    reframe_store_sdk::annotation_proto_include_dir().to_path_buf(),
    protoc_bin_vendored::include_path()?,
];

let mut config = prost_build::Config::new();
config
    .enable_type_names()
    .protoc_executable(protoc_bin_vendored::protoc_bin_path()?)
    .file_descriptor_set_path(descriptor)
    .compile_protos(&[proto], &includes)?;
```

A catalog has exactly two overview sentences and at most 4,096 entries. Every
non-topic capability needs useful guidance; functions must explicitly declare
side effects and idempotency. Protobuf methods are unary because subscriptions
stream through fixed invocation events rather than protobuf streaming. Package
verification regenerates annotation-owned metadata from the raw descriptor
bytes and rejects missing, extra, or drifted Resource/Function entries. It also
rejects missing or duplicate relationships, topic cycles, duplicate method
bindings, and Examples that do not match their method types.

```shell
cargo +1.94.0 run --locked -p reframe-store-host -- pack --store-id com.example.weather --store-version 1.0.0 --interface-major 1 --interface-minor 0 --component path/to/store.wasm --schema path/to/schema.binpb --catalog path/to/catalog.pb --output target/weather.rstore
```

The pack command creates `manifest.pb`; do not create or hash it manually. By
default its schema must contain canonical Store annotations; intentional legacy
schemas require the explicit `--legacy-catalog` flag. Output is written
atomically and will not replace an existing path unless `--force` is supplied.
It is a strict ZIP archive containing exactly these four root entries:

```text
store.wasm
manifest.pb
schema.binpb
catalog.pb
```

The builder fills the catalog identity/version fields, hashes the exact component,
schema, and catalog bytes, and then sends its own output through the install-time
verifier. The verifier rejects extra, duplicate, non-regular, oversized, or
unsupported-compression entries; invalid versions and hashes; descriptors
without source information; and catalog/schema drift. Default limits are 64 MiB
for the archive, 32 MiB for the component, 64 KiB for the manifest, 7 MiB for
the descriptor set, and 8 MiB for the catalog.

The catalog revision used by sessions and cursors is a domain-separated digest
of both the exact schema hash and catalog hash, so a schema-only update also
invalidates cached discovery projections.

`reframe-store-host verify PACKAGE...` performs all of those checks and also
compiles/pre-links each component against the pinned host world, catching an ABI
mismatch before `serve` binds an endpoint.

Before publishing a Store interface minor revision, compare it with the last
released package:

```shell
cargo +1.94.0 run --locked -p reframe-store-host -- check-compat --previous path/to/previous.rstore --candidate path/to/candidate.rstore
```

`check-compat` first applies strict package verification, then requires the same
Store ID and interface major, a non-regressing interface minor, an unchanged
minimum generic-protocol major, and a non-increasing minimum protocol minor. It
rejects removed protobuf symbols; unreserved field or enum-value removals;
field shape and RPC contract
changes; removed or reclassified capability IDs; and resource/function type,
binding, subscription, side-effect, or idempotency changes. Additive messages,
methods, optional fields, enum values, capabilities, and subscription support
remain compatible. Removed fields and enum values must reserve both their old
name and number.

See [the SDK guide](crates/store-sdk/README.md) and
[the reference Store](examples/reference-store/README.md) for the guest pattern.

## Client and framing workflow

There is deliberately no JSON or HTTP control API. A native Rust client can use
`reframe-store-protocol` with `reframe-store-transport`; another language can
generate the fixed protobuf schema in `proto/` and implement the same framing.
Agent-facing adapters should also follow the
[context discipline in the agent guide](../docs/semantic-store-agent-guide.md).

1. Connect to the platform-local endpoint. Encode one
   `reframe.semantic_store.v1.Envelope`, prefix its byte length as an unsigned
   four-byte big-endian integer, then write the protobuf bytes. Responses use
   the same framing. The default maximum encoded envelope is 8 MiB. Default
   schema and component-event limits are 7 MiB, leaving envelope headroom. The
   transport configuration is fixed when `StoreHost` is constructed. A custom
   limit that cannot carry the component-event limit or an initial Store
   response is rejected during construction, and the same proof runs before
   every later Store registration. Caller-selected discovery and inspection
   budgets are capped to the payload space left in that frame.
2. Send `OpenStoreRequest` with protocol `1.0`, an empty `session_id`, a fresh
   UUID `request_id`, sequence zero, the Store ID, supported protocol version,
   and required interface range. Retain the returned session UUID, negotiated
   version, interface version, and catalog revision.
3. For every later request, use that exact session/version, a fresh request UUID,
   and sequence zero. Start with `GetStoreCard`, then bounded `SearchCatalog` or
   `BrowseCatalog`, and inspect only selected capabilities/types. Cursors are
   opaque, authenticated, bound to the query/filter, and invalid after a catalog
   revision change. A zero page limit defaults to five and every page is capped
   at ten; zero byte budgets default to 16 KiB for lists and 64 KiB for
   inspection, and schema projections are capped at depth four.
4. Put application values in `google.protobuf.Any` with the declared fully
   qualified message name in the type URL. The host checks both the declared
   name and encoded payload against the descriptor before the request enters
   WebAssembly, and validates Data values on the way out.
5. `ReadResource`, `SubscribeResource`, and `CallFunction` responses are
   `InvocationEvent` envelopes correlated by the original request UUID. Event
   sequence numbers start at zero with Started and increase strictly. Unary
   success is Started, exactly one Data, then Complete; subscriptions may emit
   multiple Data/Progress events before Complete or Failure.
6. To cancel, send a new request envelope containing `CancelInvocationRequest`;
   its `target_request_id` is the execution request UUID. Finish with
   `CloseStoreRequest` and wait for its acknowledgement.

Sessions are owned by the connection that opened them and are deliberately
non-resumable. A session ID is rejected on every other live connection, and
EOF, transport failure, or host-initiated connection shutdown closes all of
that connection's sessions and hard-cancels their outstanding invocations.
Reconnect by opening a new session; never replay an old session UUID.

`LocalEndpoint`, `connect`, `FrameReader`, and `FrameWriter` are the public
client building blocks. One connection may carry concurrent requests; clients
must correlate responses by session/request IDs rather than assuming response
order. Protocol mistakes with valid request/session UUIDs are returned as
correlated `ProtocolError` envelopes. If a UUID itself is malformed, the host
uses a replacement request UUID and clears an invalid session ID; transport or
delivery failures close only the affected connection.

## Security and isolation boundaries

- Packages are size-bounded before allocation and exact bytes are hashed before
  protobuf decoding. Catalog method/type relationships are checked at load time.
- Unix sockets live in an owner-only `0700` directory and are mode `0600`.
  Stale-socket cleanup checks file type, device, and inode before removal.
- Windows named pipes reject remote clients, use first-instance protection, and
  carry a protected DACL granting access only to the creating owner.
- Connections enforce a hard frame ceiling, a server-wide inbound admission
  budget, a server-wide outbound byte budget, per-connection outbound fairness,
  bounded handlers, and bounded connection counts. Partial-frame reads,
  complete-frame writes, and response delivery have deadlines; idle connections
  do not time out merely for being idle.
- Discovery is deterministic and bounded. Hidden authored intent phrases affect
  lexical ranking but are never returned in catalog hits.
- Compiled components are shared by digest across loaded Store revisions. Each
  active invocation has its own Wasmtime store/instance. Cancellation aborts
  the owning execution task before serializing its terminal output, so its
  execution-context scope is per invocation rather than session-wide. Terminal
  delivery can still consume the configured response-send timeout.
- Guest events are checked for request ID, strict sequence, type, and unary or
  subscription cardinality. A guest terminal event is withheld until one more
  `next()` confirms end-of-stream, preventing post-terminal data from escaping.
- Sessions retain an immutable loaded Store revision. Re-registering a Store ID
  affects new sessions; existing sessions continue against their original
  catalog/component snapshot. Registration cannot bypass the host's fixed
  transport-frame compatibility checks.
- The component world imports WASI HTTP but not raw TCP, UDP, or filesystem
  access. HTTP/HTTPS destinations are intentionally unrestricted by the host,
  including loopback and LAN addresses; browser CORS rules do not apply.

Package signing and credentials are not implemented, and outbound HTTP can
reach services on the local machine and LAN. Only run packages whose origin and
behavior you trust.

The automated suite covers protocol, package, catalog, SDK, runtime, and
transport behavior at crate boundaries. On every host platform, CI also builds
the real reference component and runs it through local framed IPC, progressive
discovery, typed WASI HTTP, pull-driven subscription events, targeted hard
cancellation while two HTTP requests are pending, guest-trap recovery, session
close, package creation, and host ABI verification.

## Deliberately deferred

The design leaves these behind explicit future boundaries rather than hiding
provisional implementations in the host:

- persistent per-Store cache/storage imports;
- credentials and authentication material;
- large blobs, retained results, field projections, and generic result handles;
- execution-context pooling and broader guest resource limits;
- package signing and distribution policy.

The agent adapter/dynamic tool layer and Visual Panels are also outside this
workspace. They should consume this typed progressive protocol instead of
moving Store-specific control flow into the host.
