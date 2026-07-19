use super::{fields::compare_fields, index::SchemaIndex, violation::CompatibilityViolation};

pub(super) fn compare_messages(
    previous: &SchemaIndex<'_>,
    candidate: &SchemaIndex<'_>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    for (name, previous_message) in &previous.messages {
        let Some(candidate_message) = candidate.messages.get(name) else {
            violations.push(CompatibilityViolation::MessageRemoved {
                message: name.clone(),
            });
            continue;
        };
        let previous_map_entry = previous_message
            .options
            .as_ref()
            .and_then(|options| options.map_entry)
            .unwrap_or(false);
        let candidate_map_entry = candidate_message
            .options
            .as_ref()
            .and_then(|options| options.map_entry)
            .unwrap_or(false);
        if previous_map_entry != candidate_map_entry {
            violations.push(CompatibilityViolation::MessageMapEntryChanged {
                message: name.clone(),
                previous: previous_map_entry,
                candidate: candidate_map_entry,
            });
        }
        compare_fields(name, previous_message, candidate_message, violations);
    }
}
