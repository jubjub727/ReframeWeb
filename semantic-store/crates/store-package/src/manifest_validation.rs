use reframe_store_protocol::{CURRENT_PROTOCOL_VERSION, package::Manifest, validate_store_id};
use semver::Version;
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

use crate::{
    PackageError,
    archive::{CATALOG_FILE, COMPONENT_FILE, SCHEMA_FILE},
};

pub(crate) fn validate_manifest(manifest: &Manifest) -> Result<Version, PackageError> {
    validate_store_id(&manifest.store_id).map_err(PackageError::InvalidStoreId)?;
    let store_version = Version::parse(&manifest.store_version).map_err(|source| {
        PackageError::InvalidStoreVersion {
            value: manifest.store_version.clone(),
            source,
        }
    })?;
    let interface =
        manifest
            .semantic_interface_version
            .as_ref()
            .ok_or(PackageError::MissingManifestField {
                field: "semantic_interface_version",
            })?;
    interface
        .validate()
        .map_err(|_| PackageError::InvalidManifestField {
            field: "semantic_interface_version",
            reason: "major version must be non-zero",
        })?;
    let minimum =
        manifest
            .minimum_protocol_version
            .as_ref()
            .ok_or(PackageError::MissingManifestField {
                field: "minimum_protocol_version",
            })?;
    minimum
        .validate()
        .map_err(|_| PackageError::InvalidManifestField {
            field: "minimum_protocol_version",
            reason: "major version must be non-zero",
        })?;
    if !CURRENT_PROTOCOL_VERSION.supports(minimum) {
        return Err(PackageError::UnsupportedProtocol {
            major: minimum.major,
            minor: minimum.minor,
        });
    }
    Ok(store_version)
}

pub(crate) fn verify_hash(
    entry: &'static str,
    declared: &[u8],
    exact_bytes: &[u8],
) -> Result<[u8; 32], PackageError> {
    let expected: [u8; 32] =
        declared
            .try_into()
            .map_err(|_| PackageError::InvalidManifestField {
                field: hash_field(entry),
                reason: "SHA-256 digest must contain exactly 32 bytes",
            })?;
    let actual: [u8; 32] = Sha256::digest(exact_bytes).into();
    if expected.ct_eq(&actual).unwrap_u8() != 1 {
        return Err(PackageError::HashMismatch {
            entry,
            expected,
            actual,
        });
    }
    Ok(actual)
}

fn hash_field(entry: &'static str) -> &'static str {
    match entry {
        COMPONENT_FILE => "component_sha256",
        SCHEMA_FILE => "schema_sha256",
        CATALOG_FILE => "catalog_sha256",
        _ => "unknown_sha256",
    }
}
