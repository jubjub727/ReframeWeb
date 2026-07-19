//! Safe guest-side helpers for the fixed Semantic Store component boundary.
//!
//! The SDK deliberately owns no application schema. Store messages remain
//! ordinary generated protobuf types with `prost::Name` enabled at generation.

mod any;
mod error;
mod event_encoder;
mod events;
mod invocation;
mod pull;
mod request;
mod wit;

pub use any::{StoreMessage, any_type_name, pack, unpack};
pub use error::{AnyError, EventError, GuestError, RequestError};
pub use events::{BufferedInvocation, EventBuilder, InvocationMode};
pub use invocation::Invocation;
pub use pull::{InvocationSource, InvocationStep, PullInvocation};
pub use reframe_store_protocol::{annotation_proto_include_dir, annotations};
pub use request::{DecodedInvocation, InvocationOperation};
pub use wit::{semantic_store_wit_dir, semantic_store_wit_files};
