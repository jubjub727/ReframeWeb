use std::collections::BTreeMap;

use prost_reflect::DescriptorPool;
use reframe_store_protocol::package::{Catalog, CatalogEntry, Guidance, catalog_entry};

use crate::CatalogError;

pub(crate) fn validate(
    catalog: &Catalog,
    pool: &DescriptorPool,
    manifest_store_id: &str,
) -> Result<(), CatalogError> {
    let expected = super::extract::capabilities(pool, manifest_store_id)?;
    let Some(expected) = expected else {
        return Ok(());
    };
    let expected = expected
        .iter()
        .map(|entry| (entry.id.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let actual = catalog
        .entries
        .iter()
        .map(|entry| (entry.id.as_str(), entry))
        .collect::<BTreeMap<_, _>>();

    for (entry_id, expected) in &expected {
        let actual =
            actual
                .get(entry_id)
                .ok_or_else(|| CatalogError::MissingAnnotatedCapability {
                    entry_id: (*entry_id).to_owned(),
                })?;
        compare(expected, actual)?;
    }
    for entry in catalog.entries.iter().filter(|entry| {
        matches!(
            entry.kind,
            Some(catalog_entry::Kind::Resource(_)) | Some(catalog_entry::Kind::Function(_))
        )
    }) {
        if !expected.contains_key(entry.id.as_str()) {
            return Err(CatalogError::UnannotatedCapability {
                entry_id: entry.id.clone(),
            });
        }
    }
    Ok(())
}

fn compare(expected: &CatalogEntry, actual: &CatalogEntry) -> Result<(), CatalogError> {
    if expected.parent_topic_id != actual.parent_topic_id {
        return Err(drift(expected, "parent_topic_id"));
    }
    if expected.title != actual.title {
        return Err(drift(expected, "title"));
    }
    if expected.summary != actual.summary {
        return Err(drift(expected, "summary"));
    }
    if expected.intent_phrases != actual.intent_phrases {
        return Err(drift(expected, "intent_phrases"));
    }
    if expected.related_entry_ids != actual.related_entry_ids {
        return Err(drift(expected, "related_entry_ids"));
    }
    if !guidance_matches(expected.guidance.as_ref(), actual.guidance.as_ref()) {
        return Err(drift(expected, "guidance"));
    }
    match (expected.kind.as_ref(), actual.kind.as_ref()) {
        (
            Some(catalog_entry::Kind::Resource(expected_resource)),
            Some(catalog_entry::Kind::Resource(actual_resource)),
        ) => {
            if expected_resource != actual_resource {
                return Err(drift(expected, "resource"));
            }
        }
        (
            Some(catalog_entry::Kind::Function(expected_function)),
            Some(catalog_entry::Kind::Function(actual_function)),
        ) => {
            if expected_function != actual_function {
                return Err(drift(expected, "function"));
            }
        }
        _ => return Err(drift(expected, "kind")),
    }
    Ok(())
}

fn guidance_matches(expected: Option<&Guidance>, actual: Option<&Guidance>) -> bool {
    match (expected, actual) {
        (Some(expected), Some(actual)) => {
            expected.when_to_use == actual.when_to_use
                && expected.when_not_to_use == actual.when_not_to_use
                && expected.errors == actual.errors
        }
        (None, None) => true,
        _ => false,
    }
}

fn drift(entry: &CatalogEntry, field: &'static str) -> CatalogError {
    CatalogError::AnnotationDrift {
        entry_id: entry.id.clone(),
        field,
    }
}
