use std::collections::BTreeSet;

use prost::Message;
use reframe_store_protocol::{
    package::CapabilityKind,
    wire::{
        BrowseCatalogRequest, BrowseCatalogResponse, CatalogHit, GetStoreCardRequest,
        GetStoreCardResponse, SearchCatalogRequest, SearchCatalogResponse,
    },
};

use crate::{
    CatalogError, CatalogService, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT,
    budget::list_budget,
    cursor::{Operation, binding_hash},
    normalize,
    service::entry_kind,
};

impl CatalogService {
    /// Returns the intentionally minimal identity and top-level navigation card.
    pub fn get_store_card(
        &self,
        _request: &GetStoreCardRequest,
    ) -> Result<GetStoreCardResponse, CatalogError> {
        let top_level_topics = self
            .catalog
            .top_level_topic_ids
            .iter()
            .map(|id| self.entry(id).and_then(catalog_hit))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(GetStoreCardResponse {
            store_id: self.catalog.store_id.clone(),
            display_name: self.catalog.display_name.clone(),
            overview_sentences: self
                .catalog
                .overview_sentences
                .iter()
                .take(2)
                .cloned()
                .collect(),
            top_level_topics,
            semantic_interface_version: self.catalog.semantic_interface_version,
            catalog_revision: self.revision.to_vec(),
        })
    }

    /// Performs deterministic weighted lexical search over the prebuilt index.
    pub fn search_catalog(
        &self,
        request: &SearchCatalogRequest,
    ) -> Result<SearchCatalogResponse, CatalogError> {
        let terms = normalize::unique_terms(&request.query);
        let kinds = normalized_kinds(&request.kinds)?;
        let kind_bytes = kind_binding(&kinds);
        let topic = request.topic_id.trim();
        if !topic.is_empty() {
            self.ensure_topic(topic)?;
        }
        let normalized_query = terms.join("\u{1f}");
        let binding = binding_hash(&[
            normalized_query.as_bytes(),
            kind_bytes.as_slice(),
            topic.as_bytes(),
        ]);
        let offset = self.page_offset(&request.cursor, Operation::Search, &binding)?;

        let mut candidates = if terms.is_empty() {
            self.entries.keys().cloned().collect()
        } else {
            self.index.rank(&terms)
        };
        candidates.retain(|id| {
            let entry = self.entry(id).expect("index IDs come from entries");
            kind_matches(entry, &kinds)
                && (topic.is_empty() || id == topic || self.hierarchy.contains(topic, id))
        });
        let (hits, next_offset) = self.bounded_hits(
            &candidates,
            offset,
            normalized_limit(request.limit),
            list_budget(request.byte_budget)?,
        )?;
        let next_cursor = next_offset
            .map(|offset| {
                self.cursor
                    .encode(Operation::Search, offset, &self.revision, &binding)
            })
            .unwrap_or_default();
        Ok(SearchCatalogResponse {
            hits,
            next_cursor,
            catalog_revision: self.revision.to_vec(),
        })
    }

    /// Lists only immediate children of a topic (or root when the ID is empty).
    pub fn browse_catalog(
        &self,
        request: &BrowseCatalogRequest,
    ) -> Result<BrowseCatalogResponse, CatalogError> {
        let parent = request.parent_topic_id.trim();
        if !parent.is_empty() {
            self.ensure_topic(parent)?;
        }
        let kinds = normalized_kinds(&request.kinds)?;
        let kind_bytes = kind_binding(&kinds);
        let binding = binding_hash(&[parent.as_bytes(), kind_bytes.as_slice()]);
        let offset = self.page_offset(&request.cursor, Operation::Browse, &binding)?;
        let candidates = self
            .children
            .get(parent)
            .into_iter()
            .flatten()
            .filter(|id| kind_matches(self.entry(id).expect("child IDs come from entries"), &kinds))
            .cloned()
            .collect::<Vec<_>>();
        let (entries, next_offset) = self.bounded_hits(
            &candidates,
            offset,
            normalized_limit(request.limit),
            list_budget(request.byte_budget)?,
        )?;
        let next_cursor = next_offset
            .map(|offset| {
                self.cursor
                    .encode(Operation::Browse, offset, &self.revision, &binding)
            })
            .unwrap_or_default();
        Ok(BrowseCatalogResponse {
            entries,
            next_cursor,
            catalog_revision: self.revision.to_vec(),
        })
    }

    fn ensure_topic(&self, topic_id: &str) -> Result<(), CatalogError> {
        let entry = self
            .entry(topic_id)
            .map_err(|_| CatalogError::TopicNotFound {
                topic_id: topic_id.to_owned(),
            })?;
        if entry_kind(entry)? != CapabilityKind::Topic {
            return Err(CatalogError::TopicNotFound {
                topic_id: topic_id.to_owned(),
            });
        }
        Ok(())
    }

    fn page_offset(
        &self,
        cursor: &str,
        operation: Operation,
        binding: &[u8; 32],
    ) -> Result<usize, CatalogError> {
        if cursor.is_empty() {
            Ok(0)
        } else {
            self.cursor
                .decode(cursor, operation, &self.revision, binding)
        }
    }

    fn bounded_hits(
        &self,
        candidates: &[String],
        offset: usize,
        limit: usize,
        budget: usize,
    ) -> Result<(Vec<CatalogHit>, Option<usize>), CatalogError> {
        if offset > candidates.len() {
            return Err(CatalogError::InvalidCursor);
        }
        let mut hits = Vec::with_capacity(limit.min(candidates.len().saturating_sub(offset)));
        let mut used = 0_usize;
        let mut position = offset;
        while position < candidates.len() && hits.len() < limit {
            let hit = catalog_hit(self.entry(&candidates[position])?)?;
            let required = hit.encoded_len();
            if used.saturating_add(required) > budget {
                if hits.is_empty() {
                    return Err(CatalogError::BudgetExceeded { budget, required });
                }
                break;
            }
            used += required;
            hits.push(hit);
            position += 1;
        }
        let next = (position < candidates.len()).then_some(position);
        Ok((hits, next))
    }
}

pub(crate) fn catalog_hit(
    entry: &reframe_store_protocol::package::CatalogEntry,
) -> Result<CatalogHit, CatalogError> {
    Ok(CatalogHit {
        id: entry.id.clone(),
        kind: entry_kind(entry)? as i32,
        title: entry.title.clone(),
        summary: entry.summary.clone(),
    })
}

fn normalized_limit(value: u32) -> usize {
    if value == 0 {
        DEFAULT_PAGE_LIMIT
    } else {
        usize::try_from(value)
            .unwrap_or(MAX_PAGE_LIMIT)
            .min(MAX_PAGE_LIMIT)
    }
}

fn normalized_kinds(values: &[i32]) -> Result<BTreeSet<CapabilityKind>, CatalogError> {
    let mut kinds = BTreeSet::new();
    for value in values {
        let kind = CapabilityKind::try_from(*value)
            .map_err(|_| CatalogError::InvalidCapabilityKind { value: *value })?;
        if kind == CapabilityKind::Unspecified {
            return Err(CatalogError::InvalidCapabilityKind { value: *value });
        }
        kinds.insert(kind);
    }
    Ok(kinds)
}

fn kind_binding(kinds: &BTreeSet<CapabilityKind>) -> Vec<u8> {
    kinds.iter().map(|kind| *kind as u8).collect()
}

fn kind_matches(
    entry: &reframe_store_protocol::package::CatalogEntry,
    kinds: &BTreeSet<CapabilityKind>,
) -> bool {
    kinds.is_empty() || entry_kind(entry).is_ok_and(|kind| kinds.contains(&kind))
}
