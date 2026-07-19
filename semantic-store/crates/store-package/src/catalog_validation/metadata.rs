use std::collections::HashSet;

use reframe_store_protocol::package::{Catalog, CatalogEntry, Guidance, catalog_entry};

use super::{CatalogError, invalid_entry};

const MAX_ENTRIES: usize = 4_096;
const MAX_TOPICS: usize = 32;
const MAX_INTENTS: usize = 32;
const MAX_RELATED: usize = 32;
const MAX_ERRORS: usize = 16;
const MAX_EXAMPLES: usize = 8;
const MAX_ANY_BYTES: usize = 64 * 1024;

pub(super) fn validate_header(
    catalog: &Catalog,
    manifest_store_id: &str,
    manifest_interface: &reframe_store_protocol::package::InterfaceVersion,
) -> Result<(), CatalogError> {
    if catalog.format_version != super::CATALOG_FORMAT_VERSION {
        return Err(CatalogError::UnsupportedFormat {
            found: catalog.format_version,
        });
    }
    if catalog.store_id != manifest_store_id {
        return Err(CatalogError::StoreIdMismatch);
    }
    if catalog.semantic_interface_version.as_ref() != Some(manifest_interface) {
        return Err(CatalogError::InterfaceVersionMismatch);
    }
    validate_store_card(catalog)
}

pub(super) fn validate_store_card(catalog: &Catalog) -> Result<(), CatalogError> {
    if !bounded_text(&catalog.display_name, 120)
        || catalog.overview_sentences.len() != 2
        || catalog
            .overview_sentences
            .iter()
            .any(|sentence| !bounded_text(sentence, 512))
        || catalog.entries.is_empty()
        || catalog.entries.len() > MAX_ENTRIES
        || catalog.top_level_topic_ids.len() > MAX_TOPICS
    {
        return Err(CatalogError::InvalidMetadata {
            field: "store card or entry bounds",
        });
    }
    Ok(())
}

pub(super) fn validate_entry(entry: &CatalogEntry) -> Result<(), CatalogError> {
    if !valid_entry_id(&entry.id) {
        return Err(invalid_entry(entry, "id"));
    }
    if !bounded_text(&entry.title, 120) || !bounded_text(&entry.summary, 512) {
        return Err(invalid_entry(entry, "title or summary"));
    }
    if entry.kind.is_none() {
        return Err(CatalogError::MissingKind {
            entry_id: entry.id.clone(),
        });
    }
    bounded_list(
        entry,
        "intent_phrases",
        entry.intent_phrases.len(),
        MAX_INTENTS,
    )?;
    bounded_list(
        entry,
        "related_entry_ids",
        entry.related_entry_ids.len(),
        MAX_RELATED,
    )?;
    unique_bounded_text(entry, "intent_phrases", &entry.intent_phrases, 160)?;
    if entry.related_entry_ids.iter().any(|id| !valid_entry_id(id)) {
        return Err(invalid_entry(entry, "related_entry_ids"));
    }

    if !matches!(entry.kind, Some(catalog_entry::Kind::Topic(_))) {
        let guidance = entry
            .guidance
            .as_ref()
            .ok_or_else(|| CatalogError::MissingGuidance {
                entry_id: entry.id.clone(),
            })?;
        validate_guidance(entry, guidance)?;
    }
    Ok(())
}

fn validate_guidance(entry: &CatalogEntry, guidance: &Guidance) -> Result<(), CatalogError> {
    if (guidance.when_to_use.trim().is_empty() && guidance.when_not_to_use.trim().is_empty())
        || guidance.when_to_use.len() > 2_048
        || guidance.when_not_to_use.len() > 2_048
    {
        return Err(CatalogError::MissingGuidance {
            entry_id: entry.id.clone(),
        });
    }
    bounded_list(entry, "guidance.errors", guidance.errors.len(), MAX_ERRORS)?;
    bounded_list(
        entry,
        "guidance.examples",
        guidance.examples.len(),
        MAX_EXAMPLES,
    )?;

    let mut codes = HashSet::new();
    for error in &guidance.errors {
        if !bounded_text(&error.code, 64)
            || !bounded_text(&error.summary, 512)
            || error.recovery.len() > 1_024
            || !codes.insert(error.code.as_str())
        {
            return Err(invalid_entry(entry, "guidance.errors"));
        }
    }
    for example in &guidance.examples {
        if !bounded_text(&example.title, 120)
            || example.description.len() > 1_024
            || [example.input.as_ref(), example.output.as_ref()]
                .into_iter()
                .flatten()
                .any(|value| value.type_url.len() > 512 || value.value.len() > MAX_ANY_BYTES)
        {
            return Err(invalid_entry(entry, "guidance.examples"));
        }
    }
    Ok(())
}

fn bounded_list(
    entry: &CatalogEntry,
    field: &'static str,
    actual: usize,
    limit: usize,
) -> Result<(), CatalogError> {
    if actual > limit {
        return Err(CatalogError::MetadataLimit {
            entry_id: entry.id.clone(),
            field,
            limit,
        });
    }
    Ok(())
}

fn unique_bounded_text(
    entry: &CatalogEntry,
    field: &'static str,
    values: &[String],
    max_bytes: usize,
) -> Result<(), CatalogError> {
    let mut unique = HashSet::new();
    if values
        .iter()
        .any(|value| !bounded_text(value, max_bytes) || !unique.insert(value.as_str()))
    {
        return Err(invalid_entry(entry, field));
    }
    Ok(())
}

fn bounded_text(value: &str, max_bytes: usize) -> bool {
    !value.trim().is_empty() && value.len() <= max_bytes
}

fn valid_entry_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .as_bytes()
            .first()
            .is_some_and(u8::is_ascii_alphanumeric)
        && value
            .as_bytes()
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b':'))
}
