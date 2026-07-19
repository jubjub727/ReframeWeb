use std::collections::BTreeMap;

use reframe_store_package::{AuthoredCatalog, PackageBuilder, PackageError, PackageIdentity};
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    package::{CatalogEntry, InterfaceVersion, ProtocolVersion, Topic, catalog_entry},
};
use wit_component::ComponentEncoder;

pub const STORE_ID: &str = "dev.reframe.reference-store";
const INTERFACE: InterfaceVersion = InterfaceVersion { major: 1, minor: 0 };

/// Encodes a wit-bindgen core module as a validated WebAssembly Component.
pub fn componentize(module: &[u8]) -> anyhow::Result<Vec<u8>> {
    let mut encoder = ComponentEncoder::default().module(module)?.validate(true);
    encoder.encode()
}

/// Builds the deterministic reference package through the production verifier.
pub fn build_package(component: impl Into<Vec<u8>>) -> Result<Vec<u8>, PackageError> {
    let schema = include_bytes!(concat!(env!("OUT_DIR"), "/reference_store_descriptor.bin"));
    PackageBuilder::from_annotated_schema(
        identity(),
        component,
        schema.as_slice(),
        authored_catalog(),
    )?
    .build()
}

fn identity() -> PackageIdentity {
    PackageIdentity::new(
        STORE_ID,
        env!("CARGO_PKG_VERSION"),
        INTERFACE,
        ProtocolVersion {
            major: CURRENT_PROTOCOL_VERSION.major,
            minor: CURRENT_PROTOCOL_VERSION.minor,
        },
    )
}

fn authored_catalog() -> AuthoredCatalog {
    AuthoredCatalog {
        store_id: STORE_ID.to_owned(),
        display_name: "Reframe Reference Store".to_owned(),
        overview_sentences: [
            "Exercises the complete typed Semantic Store host boundary.".to_owned(),
            "Includes bounded HTTP, deterministic subscriptions, pure functions, and fault isolation."
                .to_owned(),
        ],
        entries: vec![
            topic(
                "reference.http",
                "HTTP",
                "Read bounded HTTP and HTTPS responses.",
            ),
            topic(
                "reference.streams",
                "Streams",
                "Exercise typed multi-event subscriptions.",
            ),
            topic(
                "reference.text",
                "Text",
                "Apply deterministic typed text transformations.",
            ),
            topic(
                "reference.diagnostics",
                "Diagnostics",
                "Verify component failure isolation and recovery.",
            ),
        ],
        examples_by_capability: BTreeMap::new(),
    }
}

fn topic(id: &str, title: &str, summary: &str) -> CatalogEntry {
    CatalogEntry {
        id: id.to_owned(),
        parent_topic_id: String::new(),
        title: title.to_owned(),
        summary: summary.to_owned(),
        intent_phrases: Vec::new(),
        related_entry_ids: Vec::new(),
        guidance: None,
        kind: Some(catalog_entry::Kind::Topic(Topic {})),
    }
}

#[cfg(test)]
mod tests {
    use reframe_store_package::VerifiedPackage;

    use super::*;

    #[test]
    fn deterministic_sources_build_a_verified_package() {
        let component = b"\0asm\x01\0\0\0".to_vec();
        let package = build_package(component).unwrap();
        let verified = VerifiedPackage::from_bytes(&package).unwrap();
        assert_eq!(verified.manifest().store_id, STORE_ID);
        assert_eq!(verified.catalog().entries.len(), 9);
        assert_eq!(verified.catalog().top_level_topic_ids.len(), 4);
    }
}
