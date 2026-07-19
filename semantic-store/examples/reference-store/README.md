# Reference Store

This Store is deliberately small while exercising the important host paths:

- `reference.http.loopback_snapshot` performs a bounded WASI HTTP GET against
  `localhost`, `127.0.0.0/8`, or `::1` and returns a typed response.
- `reference.http.snapshot` performs the same bounded read for an arbitrary
  absolute HTTP or HTTPS URL.
- `reference.streams.counter` supports a deterministic bounded subscription
  with typed Data and Progress events generated incrementally as the host pulls.
- `reference.text.normalize_label` is a pure idempotent Function that trims and
  collapses whitespace into a stable typed label.
- `reference.diagnostics.trap` intentionally traps after its Started event so
  conformance tests can prove per-invocation fault isolation and host recovery.
- Invalid application input becomes a domain Failure event. Malformed fixed
  protocol input uses the WIT error channel.

The component uses the [SDK-owned canonical world](../../crates/store-sdk/wit/semantic-store.wit).
Build its dedicated component crate for `wasm32-unknown-unknown`, then run the
`package-reference-store` binary with the core module path and desired
`.rstore` output path. The packager performs standard Component Model encoding,
compiles the protobuf descriptor with source information, constructs the
bounded catalog, and passes everything through the same strict `PackageBuilder`
used by installs.

The reference protobuf service is marked for
`dev.reframe.reference-store`, and its five Resource/Function entries come
only from canonical method annotations. Package source authors just the
`reference.http`, `reference.streams`, `reference.text`, and
`reference.diagnostics` topics; package verification regenerates the capability
contract from the raw descriptor and rejects drift.

The unknown-unknown target is intentional: it prevents Rust's WASI sysroot from
adding imports from a different WASI snapshot. The only imports in the encoded
component are those selected by the canonical Store WIT.

HTTP response bodies default to 256 KiB and have a hard 1 MiB limit; request
URLs are capped at 4 KiB. The loopback resource is deliberately narrow for
deterministic local integration work. The general resource accepts HTTP and
HTTPS destinations, including loopback and LAN addresses, because destination
policy belongs to package trust and host deployment rather than browser CORS.
