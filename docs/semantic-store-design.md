# Semantic Store Protocol and Runtime Design

**Status:** Planning guidance

**Date:** 2026-07-19

This document defines the intended architecture for local Semantic Stores and
gives implementation guidance without fixing an inflexible delivery sequence.
Visual Panel implementation is deliberately outside its scope.

## Purpose

A Semantic Store is an installed WebAssembly component that exposes typed
resources, functions, subscriptions, and focused usage guidance. Agents and
other clients use one generic local protocol while every Store defines its own
application messages and capabilities.

The design must provide:

- The same Store component on Linux, macOS, and Windows.
- Protobuf-typed application data without a global application object model.
- Progressive capability discovery that does not flood an agent's context.
- Direct agent use and generated client use through the same protocol.
- Asynchronous reads, calls, subscriptions, progress, and cancellation.
- Unrestricted outbound HTTP and HTTPS, including loopback and LAN services.

There are no remote Semantic Stores. Distribution downloads Store packages to
the user's computer; execution and Store communication remain local.

## Architectural Decisions

### Separate discovery, schema, and execution

The protocol has three planes:

| Plane | Responsibility |
| --- | --- |
| Catalog | Find a small set of relevant capabilities. |
| Inspection | Explain one selected capability or type. |
| Execution | Read a resource, call a function, or subscribe. |

The protocol must not provide an operation that dumps the whole Store surface
into model context. A minimal Store card, bounded search, and selective
inspection replace a monolithic Store description.

The complete descriptor set and catalog still exist for tooling. Transferring
machine-readable bytes is distinct from placing their textual representation
in a model prompt.

### Keep the runtime local and reusable

Implement the Semantic Store runtime as a reusable Rust library built around
Wasmtime and Tokio. A native application can embed that library later. During
Store-only development, a small conformance host or CLI can exercise it without
depending on Visual Panels.

Clients reach the runtime through local transports. Transport framing is not
part of Store application schemas:

- Unix-domain sockets on Linux and macOS.
- Native named pipes on Windows.
- Four-byte big-endian length followed by one encoded protocol envelope.

The runtime parses control and routing fields. It validates application type
identifiers but does not interpret Store-specific business data.

### Use WebAssembly Components

Compile each Store as a WebAssembly Component and load it with one pinned
Wasmtime release and matching WIT dependencies. The initial host boundary is:

~~~wit
interface store-api {
    resource invocation {
        next: func() -> result<option<list<u8>>, string>;
    }

    invoke: func(request: list<u8>) -> result<invocation, string>;
}

world semantic-store {
    import wasi:http/outgoing-handler;
    export store-api;
}
~~~

The byte lists contain fixed Reframe protocol messages. Discovery is served
from package metadata; only resource reads, function calls, and subscriptions
enter the component.

The runtime must drive Wasmtime asynchronously. A Store waiting for HTTP must
not block the runtime or a native UI thread.

Run each active invocation in its own Wasmtime execution context and component
instance while sharing the compiled component and host-managed persistent
state. Current Wasmtime concurrency APIs require dropping the execution Store
to hard-cancel an in-progress call; sharing one execution context across
independent invocations would therefore give cancellation the wrong scope.
**CancelInvocation** aborts the owning task and drops that execution context.
Pool execution contexts only after this lifecycle is proven correct.

### Make HTTP a normal Store capability

Supply WASI HTTP to every Store and allow any HTTP or HTTPS destination,
including localhost, loopback addresses, the LAN, and the public internet.
Do not add mandatory domain allowlists or browser CORS behavior. Do not expose
raw TCP or UDP sockets.

The Store owns fetch and cache policy. The runtime owns the portable HTTP
implementation. The exact persistent cache import, such as a per-Store
filesystem or structured storage interface, remains to be selected separately.

## Store Package

Install a versioned Store as a local .rstore archive:

~~~text
store.wasm
manifest.pb
schema.binpb
catalog.pb
~~~

**manifest.pb** identifies the Store, Store release, semantic interface version,
minimum protocol version, and exact SHA-256 hashes of the other package files.

**schema.binpb** is a google.protobuf.FileDescriptorSet containing all imports
and source information. It defines Store-specific messages and service methods.

**catalog.pb** is the bounded discovery model generated from annotated service
methods plus explicitly authored workflows.

**store.wasm** implements the declared resources and functions.

Hash exact packaged bytes. Do not decode and reserialize protobuf artifacts
before hashing because protobuf serialization is not canonical.

## Catalog Model

The catalog contains four entry kinds:

- **Topic:** a navigable grouping.
- **Resource:** selectable data that can be read and optionally subscribed to.
- **Function:** an operation with explicit side-effect and idempotency metadata.
- **Workflow:** short conditional steps referencing other catalog entries.

Every entry has a stable ID, parent topic, title, one-sentence summary, hidden
search intent phrases, and related entry IDs. Search intent phrases improve
retrieval but are not returned to the agent.

A resource declares its selector type, value type, and subscription support. A
function declares its input type, output type, side effects, and idempotency. A
workflow contains concise steps that refer to capability IDs rather than
embedding those capabilities' complete definitions.

The runtime builds a deterministic lexical search index from installed catalog
metadata. Store authors supply useful intent phrases and synonyms; runtime
search does not require an LLM call.

## Generic Protocol Surface

All messages belong to a fixed versioned protobuf package. An envelope carries
the protocol version, session ID, request ID, sequence number, and one control
message.

| Call | Principal request fields | Response |
| --- | --- | --- |
| **OpenStore** | Store ID, supported protocol version, required interface range | Bound session, chosen versions, catalog revision |
| **GetStoreCard** | Session | Minimal Store card |
| **SearchCatalog** | Query, kinds, topic, limits, cursor | Short capability hits and next cursor |
| **BrowseCatalog** | Parent topic, kinds, limits, cursor | Short child entries and next cursor |
| **InspectCapability** | Capability ID, sections, schema depth, limits | Only requested sections |
| **InspectType** | Type name, field paths, depth, limits | Bounded type view |
| **GetSchemaBundle** | Session and known artifact hash | Binary descriptor set or unchanged marker |
| **ReadResource** | Resource ID and typed selector | Invocation events |
| **SubscribeResource** | Resource ID and typed selector | Invocation events until completion or cancellation |
| **CallFunction** | Function ID, typed input, idempotency key | Invocation events |
| **CancelInvocation** | Request ID | Cancellation acknowledgement |
| **CloseStore** | Session | Close acknowledgement |

### Lifecycle

**OpenStore** negotiates the protocol version and binds a local session to a
Store ID and compatible semantic interface version.

**CloseStore** releases that session and its outstanding invocations.

Reject a protocol major mismatch, Store ID mismatch, semantic interface major
mismatch, or an installed minor version below the client's required minimum.

### Progressive discovery

**GetStoreCard** returns only Store identity, a two-sentence overview, top-level
topics, interface version, and catalog revision.

**SearchCatalog** accepts natural-language intent, optional capability kinds,
an optional topic boundary, a result limit, a UTF-8 byte budget, and an opaque
cursor. It returns only IDs, kinds, titles, and one-sentence summaries. Default
to five results and cap a page at ten.

**BrowseCatalog** lists bounded children of one topic for inspectors and clients
that need deterministic navigation.

**InspectCapability** accepts a capability ID and requested detail sections:

- Summary
- When to use
- When not to use
- Input
- Output
- Side effects
- Errors
- Examples
- Related capabilities
- Workflow steps

It also accepts schema depth, example count, and response byte limits. Unasked
sections must not be returned.

**InspectType** returns a bounded view of one protobuf type. Depth one shows
immediate fields and names nested types without recursively expanding them.
Optional field paths allow even narrower inspection.

**GetSchemaBundle** returns the complete binary descriptor set for code
generation, reflection, and validation. Agent adapters must keep it outside
model context.

Every list or search uses opaque cursors tied to the catalog revision. A Store
update invalidates old cursors and cached catalog projections.

### Execution

Use distinct semantic requests even though they share the WIT invoke function:

- **ReadResource:** resource ID plus a typed selector.
- **SubscribeResource:** resource ID plus a typed selector.
- **CallFunction:** function ID plus typed input and optional idempotency key.
- **CancelInvocation:** request ID.

Application values travel as google.protobuf.Any. The runtime verifies that the
contained type matches the catalog declaration before entering WASM.

An invocation produces ordered events:

- Started
- Data
- Progress
- Complete
- Failure

Unary operations produce one Data event followed by Complete. Subscriptions
may produce Data events until cancellation or completion. Domain failures use
the fixed protobuf failure model; WIT errors and traps indicate component or
runtime failure.

## Agent Interaction Model

An agent adapter should initially expose only narrow discovery operations. A
normal interaction is:

1. Read the minimal Store card when Store selection is necessary.
2. Search with the user's intent and a small result limit.
3. Inspect only the best candidate and only the necessary sections.
4. Inspect nested types only when their fields are needed.
5. Convert structured agent arguments into the declared protobuf input.
6. Invoke the resource or function and validate typed results.
7. Follow opaque cursors or subscriptions only while useful.

After inspection, the adapter may expose the chosen capability as a temporary
typed tool. The complete catalog, descriptor set, and unrelated capability
definitions remain in runtime or adapter memory rather than model context.

Large application results require the same discipline. The protocol may carry
full typed results without automatically inserting them into a prompt. Result
handles, field projections, and generic large-value handling should be designed
before Stores expose unbounded result sets.

The retained, context-focused operating instructions are kept separately in the
[Semantic Store Agent Guide](semantic-store-agent-guide.md).

## Store Authoring Model

Use Store-specific protobuf service and method definitions as the source of
truth even though the transport is not gRPC. Reframe custom method options
declare capabilities, while a custom service option binds each Store-owned
service to the exact manifest Store ID. This service scope prevents annotated
services brought in through descriptor imports from leaking into another
Store's catalog. Every method on a marked Store service must declare:

- Capability kind and stable ID.
- One-sentence summary and hidden intent phrases.
- Side effects and idempotency.
- Guidance or workflow references.

Input and output types come directly from method descriptors. A package builder
generates catalog.pb, preserves schema.binpb, and rejects drift between metadata
and implemented method names. Protobuf service methods remain unary; semantic
subscriptions stream through the fixed invocation event protocol instead of
protobuf streaming.

Author narrow capabilities. Prefer a resource or function that performs one
clear task over a generic method accepting arbitrary maps or JSON. Put
multi-operation guidance in workflow entries instead of repeating it across
descriptions.

## Compatibility

Version the generic protocol independently from each Store interface:

- Protocol major changes are breaking; minor versions add negotiated features.
- Store interface major changes are breaking; minor versions are additive.
- Store release versions track implementation and packaging changes.
- Schema and catalog hashes identify exact artifacts, not compatibility.

Run local protobuf breaking-change checks against the previous Store interface.
Reserve removed field numbers and names. Keep capability IDs stable across
compatible releases.

## Implementation Guidance

Organize implementation around replaceable responsibilities rather than one
large runtime crate:

- **Protocol types:** fixed envelopes, discovery calls, invocation events, and
  generated Rust bindings.
- **Package tooling:** archive reading, hashes, manifest validation, descriptor
  loading, catalog generation, and compatibility checks.
- **Runtime core:** Wasmtime configuration, component loading, request routing,
  async invocation, cancellation, and HTTP imports.
- **Catalog service:** indexing, bounded search, browsing, selective inspection,
  cursor validation, and schema projections.
- **Rust Store SDK:** guest WIT bindings, protocol helpers, metadata annotations,
  and build-time validation.
- **Conformance host:** a local CLI or test process that exercises Stores without
  any presentation layer.
- **Agent adapter:** progressive discovery, dynamic protobuf conversion, typed
  invocation, and context-safe result presentation.

An effective first vertical slice is one installed reference Store whose
resource calls an ephemeral local HTTP server and returns a typed protobuf
message. Exercise Store-card retrieval, bounded search, selective inspection,
resource reading, streaming, cancellation, and package verification through
the same runtime.

Compile each component once per runtime. Begin with one isolated execution
context per active invocation; consider safe pooling only after lifecycle and
performance measurements.

## Conformance Expectations

Run the same package and behavioral suite on Linux, macOS, and Windows. Cover:

- Package integrity and incompatible versions.
- Deterministic bounded discovery and invalid cursors.
- Selective inspection and response budgets.
- Correct application type validation.
- Unary results, streaming order, cancellation, and traps.
- HTTP calls to loopback and ordinary HTTPS endpoints.
- Cache persistence once its import is defined.
- Store update and catalog revision invalidation.

## Deferred Decisions

The following need focused designs of their own:

- Persistent Store cache and storage imports.
- Credentials and authentication material.
- Large blobs, large result retention, and result projections.
- Execution-context pooling and resource limits.
- Package signing and distribution policy.

These decisions must not alter the progressive catalog or typed invocation
contract.

## Technical Basis

- [Wasmtime platform support](https://docs.wasmtime.dev/stability-platform-support.html)
- [Wasmtime Component Model and async embedding](https://docs.wasmtime.dev/api/wasmtime/)
- [Wasmtime concurrent-call cancellation](https://docs.wasmtime.dev/api/wasmtime/component/struct.Func.html)
- [WebAssembly Component Model WIT worlds](https://component-model.bytecodealliance.org/design/worlds.html)
- [Protocol Buffer descriptor sets](https://buf.build/docs/reference/descriptors/)
- [Protocol Buffer serialization is not canonical](https://protobuf.dev/programming-guides/serialization-not-canonical/)
- [Local protobuf breaking-change checks](https://buf.build/docs/breaking/)
- [Progressive capability discovery](https://modelcontextprotocol.io/docs/develop/clients/client-best-practices)
