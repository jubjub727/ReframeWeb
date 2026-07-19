#![cfg(target_arch = "wasm32")]

mod guest;
mod wasi_http;

mod bindings {
    include!(concat!(env!("OUT_DIR"), "/semantic_store_bindings.rs"));
}

use guest::ReferenceStore;

bindings::export!(ReferenceStore with_types_in bindings);
