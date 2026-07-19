//! Reference Semantic Store used by host and package conformance tests.

mod counter_resource;
mod dispatch;
mod error;
mod http_resource;
mod http_target;
mod invocation_source;
mod model;
mod normalize_label;
#[cfg(not(target_arch = "wasm32"))]
mod package_source;

pub use dispatch::{invoke, invoke_with_http};
pub use error::ResourceError;
pub use http_resource::HttpClient;
pub use http_target::{HttpScheme, HttpTarget, LoopbackTarget};
pub use model::{
    CounterSample, CounterSelector, DiagnosticTrapInput, DiagnosticTrapOutput, HttpSnapshot,
    HttpSnapshotSelector, LoopbackSelector, LoopbackSnapshot, NormalizeLabelInput,
    NormalizeLabelOutput,
};
pub use normalize_label::FUNCTION_ID as NORMALIZE_LABEL_FUNCTION_ID;
#[cfg(not(target_arch = "wasm32"))]
pub use package_source::{STORE_ID, build_package, componentize};
