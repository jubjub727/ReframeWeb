# Reference Store component glue

This crate is the narrow Canonical ABI shell around the unsafe-free reference
Store implementation. It owns generated `wit-bindgen` exports and the WASI HTTP
adapter; application protobuf handling, dispatch, and event state live in the
parent crate.

The manifest permits unsafe code only because generated Canonical ABI shims use
it internally. No hand-authored source in this directory contains an unsafe
block or function.
