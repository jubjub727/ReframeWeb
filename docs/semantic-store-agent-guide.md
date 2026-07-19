# Semantic Store Agent Guide

Use this guide whenever you discover, call, subscribe to, create, or modify a
Semantic Store.

## Core Rule

Discover progressively. Keep the complete catalog, descriptor bundle, and
unrelated application data outside model context. Search for a few relevant
capabilities, inspect only the best candidate, then execute its declared typed
interface.

## Use an Existing Store

1. Call **GetStoreCard** only when Store selection or top-level orientation is
   necessary.
2. Call **SearchCatalog** with the user's concrete intent. Request no more than
   five results initially.
3. Call **InspectCapability** for the best candidate. Request only the sections
   needed to decide or execute.
4. Call **InspectType** at depth one for unfamiliar nested input or output types.
   Expand only required field paths.
5. Validate structured arguments against the declared protobuf input. Never
   invent fields.
6. Use **ReadResource**, **SubscribeResource**, or **CallFunction** according to
   the capability kind.
7. Follow opaque cursors without parsing them. Cancel subscriptions and
   invocations that are no longer useful.

If search is inconclusive, change the intent wording, constrain the capability
kind, or use **BrowseCatalog** inside the closest topic. Do not request the full
catalog.

## Discovery Calls

| Call | Use |
| --- | --- |
| **GetStoreCard** | Read identity, short purpose, top-level topics, and catalog revision. |
| **SearchCatalog** | Find bounded Topic, Resource, Function, or Workflow summaries. |
| **BrowseCatalog** | Navigate bounded children of one topic. |
| **InspectCapability** | Request selected guidance and shallow input/output shapes. |
| **InspectType** | Expand one protobuf type or selected fields. |
| **GetSchemaBundle** | Supply binary descriptors to code generation or validation tooling only. |

Available capability sections are:

- Summary
- WhenToUse
- WhenNotToUse
- Input
- Output
- SideEffects
- Errors
- Examples
- Related
- WorkflowSteps

Omit output details, examples, and related capabilities unless they help the
current task. Never print or inject **GetSchemaBundle** into model context.

## Capability Semantics

- Treat a **Topic** as navigation only.
- Use a **Resource** for typed selectable data. Pass its declared selector type.
- Use a **Function** for an operation. Inspect side effects and idempotency
  before calling it.
- Use a **Workflow** as concise guidance between capabilities. Inspect each
  referenced capability only when needed.
- Use a **Subscription** only while live changes matter.

Application values are protobuf messages carried as google.protobuf.Any. Supply
ordinary structured arguments to the adapter and let it validate and encode
them. Handle Started, Data, Progress, Complete, and Failure as ordered
invocation events.

Keep large results outside model context. Present only the page, fields, or
items needed for the current decision.

## Create a Store

Create a locally installed Rust WebAssembly Component.

1. Define application messages and service methods in Store-specific protobuf.
2. Give every Topic, Resource, Function, and Workflow a stable hierarchical ID.
3. Make each Resource or Function perform one clear task with narrow typed
   inputs and outputs.
4. Add a discriminative one-sentence summary and several realistic intent
   phrases. Intent phrases are search metadata, not agent-facing prose.
5. Declare side effects, idempotency, expected errors, and subscription support.
6. Put multi-call decisions in Workflow steps that reference capability IDs.
7. Generate catalog metadata from annotated method descriptors and validate
   every referenced capability and type.
8. Implement the fixed WebAssembly Component invocation interface and ordered
   event stream. Let the runtime serve discovery from package metadata.
9. Use WASI HTTP for outbound HTTP and HTTPS requests to localhost, LAN, and
   public endpoints.
10. Package these exact artifacts:

~~~text
store.wasm
manifest.pb
schema.binpb
catalog.pb
~~~

Use this component boundary:

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

The byte lists contain fixed protocol messages. Return one ordered event from
each **next** call and return none when complete. The runtime cancels an
invocation by dropping its isolated execution context; make host-backed work
safe to abandon.

The manifest identifies the Store and interface versions and hashes the exact
packaged artifacts. The descriptor bundle includes all imported protobuf files
and source information.

## Authoring Rules

- Prefer several narrow capabilities over one generic execute or query method.
- Define a concrete protobuf message for every input.
- Explain how neighboring capabilities differ.
- Keep field guidance with fields and capability guidance with capabilities.
- Keep capability IDs stable across compatible releases.
- Treat protocol-major and Store-interface-major changes as breaking.
- Reserve removed protobuf field numbers and names.
- Keep workflow steps short and inspectable by referring to capability IDs.

## Verify the Store

Confirm that an agent can:

- Find the correct capability from natural-language intent in five or fewer
  results.
- Understand and call it without loading the full catalog or schema bundle.
- Distinguish reads from side-effecting functions.
- Follow workflows through capability IDs.
- Validate inputs and receive typed results.
- Handle failure, streaming, and cancellation.
- Call HTTP endpoints on localhost and the public internet.
- Run the same Store package on Linux, macOS, and Windows.
