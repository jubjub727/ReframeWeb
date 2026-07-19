use std::io::{Cursor, Write};

use prost::Message;
use reframe_store_protocol::{
    package::{Catalog, InterfaceVersion, Manifest, ProtocolVersion},
    validate_store_id,
};
use semver::Version;
use sha2::{Digest, Sha256};
use zip::{CompressionMethod, ZipWriter, write::SimpleFileOptions};

use crate::{
    AuthoredCatalog, PackageError, PackageLimits, VerifiedPackage,
    archive::{CATALOG_FILE, COMPONENT_FILE, MANIFEST_FILE, SCHEMA_FILE},
    catalog_validation::CATALOG_FORMAT_VERSION,
    generate_catalog,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PackageIdentity {
    store_id: String,
    store_version: String,
    interface_version: InterfaceVersion,
    minimum_protocol_version: ProtocolVersion,
}

impl PackageIdentity {
    pub fn new(
        store_id: impl Into<String>,
        store_version: impl Into<String>,
        interface_version: InterfaceVersion,
        minimum_protocol_version: ProtocolVersion,
    ) -> Self {
        Self {
            store_id: store_id.into(),
            store_version: store_version.into(),
            interface_version,
            minimum_protocol_version,
        }
    }

    #[must_use]
    pub fn store_id(&self) -> &str {
        &self.store_id
    }

    #[must_use]
    pub fn store_version(&self) -> &str {
        &self.store_version
    }

    #[must_use]
    pub const fn interface_version(&self) -> &InterfaceVersion {
        &self.interface_version
    }

    #[must_use]
    pub const fn minimum_protocol_version(&self) -> &ProtocolVersion {
        &self.minimum_protocol_version
    }

    fn validate(&self) -> Result<(), PackageError> {
        validate_store_id(&self.store_id).map_err(PackageError::InvalidStoreId)?;
        Version::parse(&self.store_version).map_err(|source| {
            PackageError::InvalidStoreVersion {
                value: self.store_version.clone(),
                source,
            }
        })?;
        self.interface_version
            .validate()
            .map_err(|_| PackageError::InvalidManifestField {
                field: "semantic_interface_version",
                reason: "major version must be non-zero",
            })?;
        self.minimum_protocol_version
            .validate()
            .map_err(|_| PackageError::InvalidManifestField {
                field: "minimum_protocol_version",
                reason: "major version must be non-zero",
            })
    }
}

#[derive(Debug, Clone)]
pub struct PackageBuilder {
    identity: PackageIdentity,
    component: Vec<u8>,
    schema: Vec<u8>,
    catalog: Catalog,
}

impl PackageBuilder {
    /// Creates a builder from an explicitly authored legacy or already-generated catalog.
    pub fn from_catalog(
        identity: PackageIdentity,
        component: impl Into<Vec<u8>>,
        schema: impl Into<Vec<u8>>,
        catalog: Catalog,
    ) -> Self {
        Self {
            identity,
            component: component.into(),
            schema: schema.into(),
            catalog,
        }
    }

    /// Creates a package builder whose Resource and Function entries come from
    /// canonical protobuf method annotations in the original descriptor bytes.
    pub fn from_annotated_schema(
        identity: PackageIdentity,
        component: impl Into<Vec<u8>>,
        schema: impl Into<Vec<u8>>,
        authored: AuthoredCatalog,
    ) -> Result<Self, PackageError> {
        if authored.store_id != identity.store_id {
            return Err(PackageError::InvalidCatalog(
                crate::CatalogError::StoreIdMismatch,
            ));
        }
        let schema = schema.into();
        let catalog = generate_catalog(&schema, authored)?;
        Ok(Self::from_catalog(identity, component, schema, catalog))
    }

    pub fn build(self) -> Result<Vec<u8>, PackageError> {
        self.build_with_limits(PackageLimits::default())
    }

    pub fn build_with_limits(mut self, limits: PackageLimits) -> Result<Vec<u8>, PackageError> {
        self.identity.validate()?;
        self.catalog.format_version = CATALOG_FORMAT_VERSION;
        self.catalog.store_id.clone_from(&self.identity.store_id);
        self.catalog.semantic_interface_version = Some(self.identity.interface_version);

        let catalog_bytes = self.catalog.encode_to_vec();
        let manifest = Manifest {
            store_id: self.identity.store_id,
            store_version: self.identity.store_version,
            semantic_interface_version: Some(self.identity.interface_version),
            minimum_protocol_version: Some(self.identity.minimum_protocol_version),
            component_sha256: digest(&self.component).to_vec(),
            schema_sha256: digest(&self.schema).to_vec(),
            catalog_sha256: digest(&catalog_bytes).to_vec(),
        };
        let manifest_bytes = manifest.encode_to_vec();
        let archive = write_archive([
            (COMPONENT_FILE, self.component.as_slice()),
            (MANIFEST_FILE, manifest_bytes.as_slice()),
            (SCHEMA_FILE, self.schema.as_slice()),
            (CATALOG_FILE, catalog_bytes.as_slice()),
        ])?;

        // The builder promises that anything it emits passes the same strict path as installs.
        VerifiedPackage::from_bytes_with_limits(&archive, limits)?;
        Ok(archive)
    }

    pub fn write_to(self, mut writer: impl Write) -> Result<(), PackageError> {
        let archive = self.build()?;
        writer.write_all(&archive).map_err(PackageError::Write)
    }
}

pub(crate) fn write_archive<'a>(
    entries: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<u8>, PackageError> {
    let cursor = Cursor::new(Vec::new());
    let mut writer = ZipWriter::new(cursor);
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .unix_permissions(0o644);
    for (name, contents) in entries {
        writer.start_file(name, options)?;
        writer.write_all(contents).map_err(PackageError::Write)?;
    }
    Ok(writer.finish()?.into_inner())
}

fn digest(bytes: &[u8]) -> [u8; 32] {
    Sha256::digest(bytes).into()
}
