use std::collections::{BTreeMap, HashMap};

use reframe_store_protocol::package::Catalog;

use crate::CatalogError;

/// Linear-size preorder index for constant-time subtree membership checks.
pub(crate) struct HierarchyIndex {
    ranges: HashMap<String, NodeRange>,
}

impl HierarchyIndex {
    pub(crate) fn build(
        entries: &BTreeMap<String, usize>,
        catalog: &Catalog,
        children: &HashMap<String, Vec<String>>,
    ) -> Result<Self, CatalogError> {
        let mut roots = catalog
            .entries
            .iter()
            .filter(|entry| entry.parent_topic_id.is_empty())
            .map(|entry| entry.id.clone())
            .collect::<Vec<_>>();
        roots.sort_unstable();

        let mut ranges = HashMap::with_capacity(entries.len());
        let mut stack = roots
            .into_iter()
            .rev()
            .map(Frame::Enter)
            .collect::<Vec<_>>();
        let mut position = 0_usize;
        while let Some(frame) = stack.pop() {
            match frame {
                Frame::Enter(id) => {
                    if ranges.contains_key(&id) {
                        return Err(cycle_error());
                    }
                    let start = position;
                    position = position.checked_add(1).ok_or(cycle_error())?;
                    ranges.insert(id.clone(), NodeRange { start, end: start });
                    stack.push(Frame::Exit(id.clone()));
                    if let Some(child_ids) = children.get(&id) {
                        stack.extend(child_ids.iter().rev().cloned().map(Frame::Enter));
                    }
                }
                Frame::Exit(id) => {
                    ranges.get_mut(&id).expect("entered nodes have a range").end = position;
                }
            }
        }
        if ranges.len() != entries.len() {
            return Err(cycle_error());
        }
        Ok(Self { ranges })
    }

    pub(crate) fn contains(&self, ancestor_id: &str, candidate_id: &str) -> bool {
        let (Some(ancestor), Some(candidate)) =
            (self.ranges.get(ancestor_id), self.ranges.get(candidate_id))
        else {
            return false;
        };
        candidate.start >= ancestor.start && candidate.start < ancestor.end
    }
}

struct NodeRange {
    start: usize,
    end: usize,
}

enum Frame {
    Enter(String),
    Exit(String),
}

const fn cycle_error() -> CatalogError {
    CatalogError::InvalidCatalog {
        reason: "the topic hierarchy contains a cycle",
    }
}

#[cfg(test)]
mod tests {
    use reframe_store_protocol::package::{CatalogEntry, Topic, catalog_entry};

    use super::*;

    #[test]
    fn deeply_nested_catalogs_use_an_iterative_linear_index() {
        const ENTRY_COUNT: usize = 4_096;
        let mut entries = BTreeMap::new();
        let mut catalog_entries = Vec::new();
        let mut children = HashMap::<String, Vec<String>>::new();
        for index in 0..ENTRY_COUNT {
            let id = format!("topic.{index:04}");
            let parent = if index > 0 {
                format!("topic.{:04}", index - 1)
            } else {
                String::new()
            };
            children.entry(parent.clone()).or_default().push(id.clone());
            entries.insert(id.clone(), index);
            catalog_entries.push(CatalogEntry {
                id,
                parent_topic_id: parent,
                kind: Some(catalog_entry::Kind::Topic(Topic {})),
                ..CatalogEntry::default()
            });
        }

        let catalog = Catalog {
            entries: catalog_entries,
            ..Catalog::default()
        };
        let hierarchy =
            HierarchyIndex::build(&entries, &catalog, &children).expect("valid hierarchy");
        assert_eq!(hierarchy.ranges.len(), ENTRY_COUNT);
        assert!(hierarchy.contains("topic.0000", "topic.4095"));
        assert!(!hierarchy.contains("topic.4095", "topic.0000"));
    }
}
