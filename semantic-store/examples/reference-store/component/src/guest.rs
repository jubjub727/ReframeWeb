#![forbid(unsafe_code)]

use reframe_reference_store::invoke_with_http;
use reframe_store_sdk::Invocation as StoreInvocation;

use crate::{
    bindings::exports::reframe::semantic_store::store_api::{Guest, GuestInvocation, Invocation},
    wasi_http::WasiHttp,
};

pub(crate) struct ReferenceStore;

impl Guest for ReferenceStore {
    type Invocation = StoreInvocation;

    fn invoke(request: Vec<u8>) -> Result<Invocation, String> {
        invoke_with_http(&request, WasiHttp)
            .map(Invocation::new)
            .map_err(reframe_store_sdk::GuestError::into_wit_string)
    }
}

impl GuestInvocation for StoreInvocation {
    fn next(&self) -> Result<Option<Vec<u8>>, String> {
        self.next().map_err(|error| error.to_string())
    }
}
