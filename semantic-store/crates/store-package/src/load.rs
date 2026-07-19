use std::{collections::HashMap, io::Read, sync::Arc};

use prost::Message;
use prost_reflect::DescriptorPool;
use prost_types::FileDescriptorSet;
use reframe_store_protocol::PayloadShapeError;
use reframe_store_protocol::package::{Catalog, InterfaceVersion, Manifest};
use semver::Version;
use sha2::{Digest, Sha256};

use crate::{
    PackageError, PackageLimits,
    archive::{CATALOG_FILE, COMPONENT_FILE, MANIFEST_FILE, SCHEMA_FILE, read_archive},
    catalog_validation::validate_catalog,
    manifest_validation::{validate_manifest, verify_hash},
    protobuf_shape,
};

#[derive(Clone)]
pub struct VerifiedPackage {
    manifest: Arc<Manifest>,
    catalog: Arc<Catalog>,
    descriptor_set: Arc<FileDescriptorSet>,
    descriptor_pool: DescriptorPool,
    store_version: Version,
    component: Arc<[u8]>,
    manifest_bytes: Arc<[u8]>,
    schema_bytes: Arc<[u8]>,
    catalog_bytes: Arc<[u8]>,
    component_hash: [u8; 32],
    schema_hash: [u8; 32],
    catalog_revision: [u8; 32],
}

impl std::fmt::Debug for VerifiedPackage {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("VerifiedPackage")
            .field("store_id", &self.manifest.store_id)
            .field("store_version", &self.store_version)
            .field("component_bytes", &self.component.len())
            .field("schema_bytes", &self.schema_bytes.len())
            .field("catalog_bytes", &self.catalog_bytes.len())
            .finish_non_exhaustive()
    }
}

impl VerifiedPackage {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, PackageError> {
        Self::from_bytes_with_limits(bytes, PackageLimits::default())
    }

    pub fn from_bytes_with_limits(
        bytes: &[u8],
        limits: PackageLimits,
    ) -> Result<Self, PackageError> {
        let actual = u64::try_from(bytes.len()).unwrap_or(u64::MAX);
        if actual > limits.max_archive_bytes {
            return Err(PackageError::ArchiveTooLarge {
                actual,
                limit: limits.max_archive_bytes,
            });
        }
        Self::verify(read_archive(bytes, limits)?)
    }

    pub fn read(reader: impl Read, limits: PackageLimits) -> Result<Self, PackageError> {
        let mut bytes = Vec::new();
        reader
            .take(limits.max_archive_bytes.saturating_add(1))
            .read_to_end(&mut bytes)
            .map_err(|source| PackageError::EntryRead {
                name: "<archive>",
                source,
            })?;
        Self::from_bytes_with_limits(&bytes, limits)
    }

    fn verify(mut files: HashMap<&'static str, Vec<u8>>) -> Result<Self, PackageError> {
        let manifest_bytes = take_file(&mut files, MANIFEST_FILE)?;
        let component = take_file(&mut files, COMPONENT_FILE)?;
        let schema_bytes = take_file(&mut files, SCHEMA_FILE)?;
        let catalog_bytes = take_file(&mut files, CATALOG_FILE)?;

        protobuf_shape::validate_manifest(&manifest_bytes)
            .map_err(|error| shape_error(MANIFEST_FILE, error, PackageError::ManifestDecode))?;
        let manifest =
            Manifest::decode(manifest_bytes.as_slice()).map_err(PackageError::ManifestDecode)?;
        let store_version = validate_manifest(&manifest)?;
        let component_hash = verify_hash(
            COMPONENT_FILE,
            &manifest.component_sha256,
            component.as_slice(),
        )?;
        let schema_hash = verify_hash(
            SCHEMA_FILE,
            &manifest.schema_sha256,
            schema_bytes.as_slice(),
        )?;
        let catalog_hash = verify_hash(
            CATALOG_FILE,
            &manifest.catalog_sha256,
            catalog_bytes.as_slice(),
        )?;
        let catalog_revision = discovery_revision(schema_hash, catalog_hash);

        // No descriptor or catalog decoding occurs before exact-byte hash verification.
        protobuf_shape::validate_schema(&schema_bytes)
            .map_err(|error| shape_error(SCHEMA_FILE, error, PackageError::SchemaDecode))?;
        protobuf_shape::validate_catalog(&catalog_bytes)
            .map_err(|error| shape_error(CATALOG_FILE, error, PackageError::CatalogDecode))?;
        let descriptor_set = FileDescriptorSet::decode(schema_bytes.as_slice())
            .map_err(PackageError::SchemaDecode)?;
        validate_source_info(&descriptor_set)?;
        // Decode the exact artifact bytes so registered custom options survive.
        let descriptor_pool = DescriptorPool::decode(schema_bytes.as_slice())
            .map_err(PackageError::InvalidDescriptorSet)?;
        let catalog =
            Catalog::decode(catalog_bytes.as_slice()).map_err(PackageError::CatalogDecode)?;
        validate_catalog(
            &catalog,
            &manifest.store_id,
            manifest
                .semantic_interface_version
                .as_ref()
                .expect("manifest validated"),
            &descriptor_pool,
        )?;

        Ok(Self {
            manifest: Arc::new(manifest),
            catalog: Arc::new(catalog),
            descriptor_set: Arc::new(descriptor_set),
            descriptor_pool,
            store_version,
            component: component.into(),
            manifest_bytes: manifest_bytes.into(),
            schema_bytes: schema_bytes.into(),
            catalog_bytes: catalog_bytes.into(),
            component_hash,
            schema_hash,
            catalog_revision,
        })
    }

    #[must_use]
    pub fn manifest(&self) -> &Manifest {
        &self.manifest
    }
    #[must_use]
    pub fn catalog(&self) -> &Catalog {
        &self.catalog
    }
    /// Shares the immutable decoded catalog without cloning its protobuf data.
    #[must_use]
    pub fn catalog_arc(&self) -> Arc<Catalog> {
        Arc::clone(&self.catalog)
    }
    #[must_use]
    pub fn descriptor_set(&self) -> &FileDescriptorSet {
        &self.descriptor_set
    }
    #[must_use]
    pub const fn descriptor_pool(&self) -> &DescriptorPool {
        &self.descriptor_pool
    }
    #[must_use]
    pub const fn store_version(&self) -> &Version {
        &self.store_version
    }
    #[must_use]
    pub fn interface_version(&self) -> &InterfaceVersion {
        self.manifest
            .semantic_interface_version
            .as_ref()
            .expect("verified")
    }
    #[must_use]
    pub fn component_bytes(&self) -> &[u8] {
        &self.component
    }
    #[must_use]
    pub fn manifest_bytes(&self) -> &[u8] {
        &self.manifest_bytes
    }
    #[must_use]
    pub fn schema_bytes(&self) -> &[u8] {
        &self.schema_bytes
    }
    /// Shares the exact immutable descriptor bytes without copying the artifact.
    #[must_use]
    pub fn schema_bytes_arc(&self) -> Arc<[u8]> {
        Arc::clone(&self.schema_bytes)
    }
    #[must_use]
    pub fn catalog_bytes(&self) -> &[u8] {
        &self.catalog_bytes
    }
    #[must_use]
    pub const fn component_hash(&self) -> [u8; 32] {
        self.component_hash
    }
    #[must_use]
    pub const fn schema_hash(&self) -> [u8; 32] {
        self.schema_hash
    }
    /// Returns the discovery revision derived from both exact schema and catalog bytes.
    #[must_use]
    pub const fn catalog_revision(&self) -> [u8; 32] {
        self.catalog_revision
    }
}

fn discovery_revision(schema_hash: [u8; 32], catalog_hash: [u8; 32]) -> [u8; 32] {
    let mut digest = Sha256::new();
    digest.update(b"reframe.semantic-store.catalog-revision.v1\0");
    digest.update(schema_hash);
    digest.update(catalog_hash);
    digest.finalize().into()
}

fn validate_source_info(set: &FileDescriptorSet) -> Result<(), PackageError> {
    if set.file.is_empty() {
        return Err(PackageError::EmptySchema);
    }
    for file in &set.file {
        if file
            .source_code_info
            .as_ref()
            .is_none_or(|info| info.location.is_empty())
        {
            return Err(PackageError::MissingSourceInfo {
                file: file.name.clone().unwrap_or_else(|| "<unnamed>".to_owned()),
            });
        }
    }
    Ok(())
}

fn take_file(
    files: &mut HashMap<&'static str, Vec<u8>>,
    name: &'static str,
) -> Result<Vec<u8>, PackageError> {
    files
        .remove(name)
        .ok_or(PackageError::MissingEntry { name })
}

fn shape_error(
    entry: &'static str,
    error: PayloadShapeError,
    decode_error: fn(prost::DecodeError) -> PackageError,
) -> PackageError {
    match error {
        PayloadShapeError::Decode(source) => decode_error(source),
        source => PackageError::ProtobufShape { entry, source },
    }
}
