use std::collections::{BTreeMap, BTreeSet, HashMap};

use reframe_store_protocol::package::CatalogEntry;

use crate::normalize;

/// Score contributed once when a query term appears in a capability ID.
pub const ID_WEIGHT: u32 = 8;
/// Score contributed once when a query term appears in a title.
pub const TITLE_WEIGHT: u32 = 6;
/// Score contributed once when a query term appears in hidden authored intents.
pub const INTENT_WEIGHT: u32 = 4;
/// Score contributed once when a query term appears in a one-sentence summary.
pub const SUMMARY_WEIGHT: u32 = 2;

#[derive(Debug, Clone)]
struct Posting {
    entry_index: usize,
    weight: u32,
}

/// An immutable inverted index. Tokens repeated within one authored field do
/// not inflate rank; matches across distinct fields intentionally accumulate.
#[derive(Debug)]
pub(crate) struct SearchIndex {
    entry_ids: Vec<String>,
    postings: HashMap<String, Vec<Posting>>,
}

impl SearchIndex {
    pub(crate) fn build<'a>(entries: impl Iterator<Item = &'a CatalogEntry>) -> Self {
        let mut postings: HashMap<String, Vec<Posting>> = HashMap::new();
        let mut entry_ids = Vec::new();
        for (entry_index, entry) in entries.enumerate() {
            entry_ids.push(entry.id.clone());
            let mut weights = BTreeMap::<String, u32>::new();
            add_field(&mut weights, &entry.id, ID_WEIGHT);
            add_field(&mut weights, &entry.title, TITLE_WEIGHT);
            add_field(&mut weights, &entry.summary, SUMMARY_WEIGHT);
            let intent_terms = entry
                .intent_phrases
                .iter()
                .flat_map(|phrase| normalize::terms(phrase))
                .collect::<BTreeSet<_>>();
            for term in intent_terms {
                weights
                    .entry(term)
                    .and_modify(|total| *total = total.saturating_add(INTENT_WEIGHT))
                    .or_insert(INTENT_WEIGHT);
            }
            for (term, weight) in weights {
                postings.entry(term).or_default().push(Posting {
                    entry_index,
                    weight,
                });
            }
        }
        Self {
            entry_ids,
            postings,
        }
    }

    pub(crate) fn rank(&self, query_terms: &[String]) -> Vec<String> {
        let mut scores = HashMap::<usize, u32>::new();
        for term in query_terms {
            if let Some(postings) = self.postings.get(term) {
                for posting in postings {
                    scores
                        .entry(posting.entry_index)
                        .and_modify(|score| *score = score.saturating_add(posting.weight))
                        .or_insert(posting.weight);
                }
            }
        }
        let mut ranked: Vec<_> = scores.into_iter().collect();
        ranked.sort_unstable_by(|(left_index, left_score), (right_index, right_score)| {
            right_score
                .cmp(left_score)
                .then_with(|| self.entry_ids[*left_index].cmp(&self.entry_ids[*right_index]))
        });
        ranked
            .into_iter()
            .map(|(entry_index, _)| self.entry_ids[entry_index].clone())
            .collect()
    }
}

fn add_field(weights: &mut BTreeMap<String, u32>, value: &str, weight: u32) {
    for term in normalize::terms(value).into_iter().collect::<BTreeSet<_>>() {
        weights
            .entry(term)
            .and_modify(|total| *total = total.saturating_add(weight))
            .or_insert(weight);
    }
}

#[cfg(test)]
mod tests {
    use reframe_store_protocol::package::{CatalogEntry, Topic, catalog_entry};

    use super::*;

    fn entry(id: &str, title: &str, summary: &str, intents: &[&str]) -> CatalogEntry {
        CatalogEntry {
            id: id.to_owned(),
            title: title.to_owned(),
            summary: summary.to_owned(),
            intent_phrases: intents.iter().map(ToString::to_string).collect(),
            kind: Some(catalog_entry::Kind::Topic(Topic {})),
            ..Default::default()
        }
    }

    #[test]
    fn ranking_uses_weights_then_stable_id_tie_break() {
        let entries = [
            entry("z-id", "calendar", "x", &[]),
            entry("a-id", "calendar", "x", &[]),
            entry("calendar-id", "other", "x", &[]),
        ];
        let index = SearchIndex::build(entries.iter());
        assert_eq!(
            index.rank(&["calendar".to_owned()]),
            ["calendar-id", "a-id", "z-id"]
        );
    }
}
