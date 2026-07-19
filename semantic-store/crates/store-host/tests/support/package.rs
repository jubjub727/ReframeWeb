use std::{env, path::PathBuf};

use anyhow::{Context, Result};
use reframe_reference_store::{build_package, componentize};
use reframe_store_package::{PackageBuilder, PackageIdentity, VerifiedPackage};
use reframe_store_protocol::package::catalog_entry;

pub(crate) fn reference_package() -> Result<VerifiedPackage> {
    let core_path = env::var_os("REFRAME_REFERENCE_CORE_WASM")
        .map(PathBuf::from)
        .unwrap_or_else(default_core_path);
    let core = std::fs::read(&core_path).with_context(|| {
        format!(
            "reference core module is missing at {}; build reframe-reference-store-component for wasm32-unknown-unknown first",
            core_path.display()
        )
    })?;
    let component =
        componentize(&core).context("reference core module could not be componentized")?;
    let package = build_package(component).context("reference package could not be built")?;
    VerifiedPackage::from_bytes(&package).context("reference package did not verify")
}

pub(crate) fn package_with_schema_padding(
    source: &VerifiedPackage,
    padding: usize,
) -> Result<VerifiedPackage> {
    let mut schema = source.schema_bytes().to_vec();
    append_length_delimited_unknown_field(&mut schema, 50_000, padding);

    let identity = PackageIdentity::new(
        source.manifest().store_id.clone(),
        source.store_version().to_string(),
        *source.interface_version(),
        *source
            .manifest()
            .minimum_protocol_version
            .as_ref()
            .context("verified package has no minimum protocol version")?,
    );
    let archive = PackageBuilder::from_catalog(
        identity,
        source.component_bytes(),
        schema,
        source.catalog().clone(),
    )
    .build()
    .context("padded reference package could not be built")?;
    VerifiedPackage::from_bytes(&archive).context("padded reference package did not verify")
}

pub(crate) fn package_with_updated_topic(source: &VerifiedPackage) -> Result<VerifiedPackage> {
    let mut catalog = source.catalog().clone();
    let topic = catalog
        .entries
        .iter_mut()
        .find(|entry| {
            entry.id == "reference.text"
                && matches!(entry.kind, Some(catalog_entry::Kind::Topic(_)))
        })
        .context("reference text topic is missing")?;
    topic.title = "Text normalization tools".to_owned();

    let identity = PackageIdentity::new(
        source.manifest().store_id.clone(),
        "0.1.1",
        *source.interface_version(),
        *source
            .manifest()
            .minimum_protocol_version
            .as_ref()
            .context("verified package has no minimum protocol version")?,
    );
    let archive = PackageBuilder::from_catalog(
        identity,
        source.component_bytes(),
        source.schema_bytes(),
        catalog,
    )
    .build()
    .context("updated reference package could not be built")?;
    VerifiedPackage::from_bytes(&archive).context("updated reference package did not verify")
}

// Padding the original bytes keeps custom method-option payloads intact. A
// prost_types decode/re-encode round trip would discard those extensions.
fn append_length_delimited_unknown_field(bytes: &mut Vec<u8>, field_number: u32, length: usize) {
    encode_varint(u64::from(field_number) << 3 | 2, bytes);
    encode_varint(u64::try_from(length).unwrap_or(u64::MAX), bytes);
    bytes.resize(bytes.len().saturating_add(length), 0);
}

fn encode_varint(mut value: u64, output: &mut Vec<u8>) {
    while value >= 0x80 {
        output.push((value as u8 & 0x7f) | 0x80);
        value >>= 7;
    }
    output.push(value as u8);
}

fn default_core_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/wasm32-unknown-unknown/release/reframe_reference_store_component.wasm")
}
