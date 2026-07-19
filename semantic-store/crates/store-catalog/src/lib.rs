//! Deterministic, bounded discovery over verified Semantic Store metadata.
//!
//! [`CatalogService`] is immutable after construction. It prepares its lexical
//! index and topic hierarchy once, then serves discovery, inspection, schema,
//! and invocation-validation requests without rescanning authored search text.

mod budget;
mod capability;
mod cursor;
mod discovery;
mod error;
mod field_selection;
mod hierarchy;
mod index;
mod invocation;
mod normalize;
mod schema;
mod service;
mod type_projection;
#[cfg(test)]
mod type_projection_tests;
mod type_view;

pub use cursor::CursorAuthority;
pub use error::CatalogError;
pub use index::{ID_WEIGHT, INTENT_WEIGHT, SUMMARY_WEIGHT, TITLE_WEIGHT};
pub use invocation::{InvocationContract, InvocationMode};
pub use service::CatalogService;

/// Default number of results in a search or browse page.
pub const DEFAULT_PAGE_LIMIT: usize = 5;
/// Hard limit for a search or browse page.
pub const MAX_PAGE_LIMIT: usize = 10;
/// Default encoded-entry budget for a search or browse page.
pub const DEFAULT_LIST_BYTE_BUDGET: usize = 16 * 1024;
/// Default encoded response budget for inspection operations.
pub const DEFAULT_INSPECTION_BYTE_BUDGET: usize = 64 * 1024;
/// Hard encoded-response and projection-work ceiling for inspection operations.
pub const MAX_INSPECTION_BYTE_BUDGET: usize = 7 * 1024 * 1024;
/// Default number of examples returned when the examples section is requested.
pub const DEFAULT_EXAMPLE_LIMIT: usize = 1;
/// Hard recursion limit for descriptor projections.
pub const MAX_SCHEMA_DEPTH: usize = 4;
