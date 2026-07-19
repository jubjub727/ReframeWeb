# Reframe Store SDK

Guest-side Rust helpers for the fixed Semantic Store component interface. The
SDK decodes and validates host requests, packs typed protobuf messages into
`google.protobuf.Any`, and constructs complete ordered invocation streams.
Generated Store messages need `prost::Name`; enable it once in the Store's
build script instead of maintaining type-name constants by hand:

```rust
let mut config = prost_build::Config::new();
config.enable_type_names();
config.compile_protos(&["proto/store.proto"], &["proto"])?;
```

For small results, build a complete stream eagerly:

```rust
let request = DecodedInvocation::decode(&request_bytes)?;
let selector: MySelector = request.input()?;

let mut events = EventBuilder::for_request(&request)?;
events.data(&load_value(selector)?)?;
let invocation = events.complete()?;
```

For subscriptions, slow I/O, or large result sets, retain application state and
advance it exactly once per host pull:

```rust
struct Series { /* cursor and application state */ }

impl InvocationSource for Series {
    fn next(&mut self) -> Result<InvocationStep, GuestError> {
        // Return one Data or Progress step per pull until the source is done.
        Ok(InvocationStep::Complete)
    }
}

let invocation: Invocation = PullInvocation::for_request(&request, Series { /* ... */ })?.into();
```

Both forms map directly to the WIT `invocation.next` method. The first pull
returns Started; the SDK assigns strict sequence numbers, validates unary
cardinality, enforces a single terminal event, and never polls an application
source after termination. This keeps host backpressure real: slow work begins
only when the host requests the next application event.

The canonical WIT package ships inside this crate at `wit/`. Build scripts can
use `semantic_store_wit_dir()` for bindgen and
`semantic_store_wit_files()` for deterministic `rerun-if-changed` coverage;
consumers do not need a workspace-relative WIT path.

Store method metadata uses the canonical
`reframe/semantic_store/options/v1/annotations.proto` custom option. Build
scripts can pass [`annotation_proto_include_dir`](src/lib.rs) to protoc instead
of copying that schema into each Store. When using the vendored protoc binary,
also include `protoc_bin_vendored::include_path()` so its
`google/protobuf/descriptor.proto` import resolves. Descriptor consumers must
decode the original descriptor-set bytes with `prost_reflect::DescriptorPool::decode`;
decoding through `prost_types::FileDescriptorSet` first discards custom-option
payloads.

Cargo releases are protocol-first: publish the matching
`reframe-store-protocol` version before `reframe-store-sdk`. The SDK dependency
uses both a workspace path and an exact compatible package version so local
development and published resolution share the same contract.

Mark every Store-owned protobuf service with the canonical `store_service`
option and its exact Store ID, then put one `capability` option on each unary
Resource or Function method. The package generator uses that service marker to
ignore annotated imported services belonging to other Stores, derives method
bindings and message types, and rejects unspecified Function semantics. Topics,
Workflows, and typed Examples remain explicitly authored outside the service
descriptor.
