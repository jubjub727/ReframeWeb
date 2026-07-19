use std::collections::HashSet;

use reframe_store_protocol::package::{Catalog, catalog_entry};

use super::{CatalogError, EntryMap, invalid_entry, missing_relation};

pub(super) fn validate(catalog: &Catalog, entries: &EntryMap<'_>) -> Result<(), CatalogError> {
    validate_top_level_topics(catalog, entries)?;
    validate_links(entries)?;
    validate_parent_cycles(entries)
}

fn validate_top_level_topics(
    catalog: &Catalog,
    entries: &EntryMap<'_>,
) -> Result<(), CatalogError> {
    let mut declared = HashSet::new();
    for id in &catalog.top_level_topic_ids {
        let Some(entry) = entries.get(id.as_str()) else {
            return Err(CatalogError::InvalidTopLevelTopic {
                entry_id: id.clone(),
            });
        };
        if !entry.parent_topic_id.is_empty()
            || !matches!(entry.kind, Some(catalog_entry::Kind::Topic(_)))
            || !declared.insert(id.as_str())
        {
            return Err(CatalogError::InvalidTopLevelTopic {
                entry_id: id.clone(),
            });
        }
    }
    for entry in entries.values() {
        if matches!(entry.kind, Some(catalog_entry::Kind::Topic(_)))
            && entry.parent_topic_id.is_empty()
            && !declared.contains(entry.id.as_str())
        {
            return Err(CatalogError::MissingTopLevelTopic {
                entry_id: entry.id.clone(),
            });
        }
    }
    Ok(())
}

fn validate_links(entries: &EntryMap<'_>) -> Result<(), CatalogError> {
    for entry in entries.values() {
        if entry.parent_topic_id.is_empty() {
            if !matches!(entry.kind, Some(catalog_entry::Kind::Topic(_))) {
                return Err(invalid_entry(entry, "parent_topic_id"));
            }
        } else {
            let Some(parent) = entries.get(entry.parent_topic_id.as_str()) else {
                return Err(missing_relation(entry, "parent", &entry.parent_topic_id));
            };
            if !matches!(parent.kind, Some(catalog_entry::Kind::Topic(_))) {
                return Err(CatalogError::ParentNotTopic {
                    entry_id: entry.id.clone(),
                    parent_id: parent.id.clone(),
                });
            }
        }

        let mut related = HashSet::new();
        for target in &entry.related_entry_ids {
            if target == &entry.id {
                return Err(CatalogError::SelfRelation {
                    entry_id: entry.id.clone(),
                });
            }
            if !related.insert(target.as_str()) {
                return Err(CatalogError::DuplicateRelation {
                    entry_id: entry.id.clone(),
                    relation: "related entry",
                    target_id: target.clone(),
                });
            }
            if !entries.contains_key(target.as_str()) {
                return Err(missing_relation(entry, "related entry", target));
            }
        }
    }
    Ok(())
}

fn validate_parent_cycles(entries: &EntryMap<'_>) -> Result<(), CatalogError> {
    for entry in entries.values() {
        let mut seen = HashSet::new();
        let mut current = *entry;
        while !current.parent_topic_id.is_empty() {
            if !seen.insert(current.id.as_str()) {
                return Err(CatalogError::ParentCycle {
                    entry_id: current.id.clone(),
                });
            }
            current = entries[&current.parent_topic_id.as_str()];
        }
    }
    Ok(())
}
