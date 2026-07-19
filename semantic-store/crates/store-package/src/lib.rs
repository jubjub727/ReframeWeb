//! Strict loading and creation of verified `.rstore` archives.

mod annotated_catalog;
mod archive;
mod catalog_validation;
mod compatibility;
mod error;
mod load;
mod manifest_validation;
mod protobuf_shape;
mod write;

#[cfg(test)]
mod annotated_catalog_tests;
#[cfg(test)]
mod archive_tests;
#[cfg(test)]
mod protobuf_shape_tests;
#[cfg(test)]
mod semantic_tests;
#[cfg(test)]
mod test_fixture;

pub use annotated_catalog::{AuthoredCatalog, generate_catalog, schema_uses_annotations};
pub use archive::PackageLimits;
pub use catalog_validation::CatalogError;
pub use compatibility::{
    CompatibilityError, CompatibilityIssues, CompatibilityViolation, check_package_compatibility,
};
pub use error::PackageError;
pub use load::VerifiedPackage;
pub use write::{PackageBuilder, PackageIdentity};
