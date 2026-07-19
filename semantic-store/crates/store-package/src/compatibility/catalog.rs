use std::collections::BTreeMap;

use reframe_store_protocol::package::{Catalog, CatalogEntry, catalog_entry};

use super::violation::CompatibilityViolation;

pub(super) fn compare_catalog(
    previous: &Catalog,
    candidate: &Catalog,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let candidate_entries = candidate
        .entries
        .iter()
        .map(|entry| (entry.id.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let mut previous_entries = previous.entries.iter().collect::<Vec<_>>();
    previous_entries.sort_unstable_by_key(|entry| entry.id.as_str());
    for previous_entry in previous_entries {
        let Some(candidate_entry) = candidate_entries.get(previous_entry.id.as_str()) else {
            violations.push(CompatibilityViolation::CapabilityRemoved {
                capability_id: previous_entry.id.clone(),
            });
            continue;
        };
        let previous_kind = kind_name(previous_entry);
        let candidate_kind = kind_name(candidate_entry);
        if previous_kind != candidate_kind {
            violations.push(CompatibilityViolation::CapabilityKindChanged {
                capability_id: previous_entry.id.clone(),
                previous: previous_kind.to_owned(),
                candidate: candidate_kind.to_owned(),
            });
            continue;
        }
        match (&previous_entry.kind, &candidate_entry.kind) {
            (
                Some(catalog_entry::Kind::Resource(previous)),
                Some(catalog_entry::Kind::Resource(candidate)),
            ) => compare_resource(&previous_entry.id, previous, candidate, violations),
            (
                Some(catalog_entry::Kind::Function(previous)),
                Some(catalog_entry::Kind::Function(candidate)),
            ) => compare_function(&previous_entry.id, previous, candidate, violations),
            _ => {}
        }
    }
}

fn compare_resource(
    capability_id: &str,
    previous: &reframe_store_protocol::package::Resource,
    candidate: &reframe_store_protocol::package::Resource,
    violations: &mut Vec<CompatibilityViolation>,
) {
    compare_type(
        capability_id,
        "selector",
        &previous.selector_type,
        &candidate.selector_type,
        violations,
    );
    compare_type(
        capability_id,
        "value",
        &previous.value_type,
        &candidate.value_type,
        violations,
    );
    compare_binding(
        capability_id,
        previous.method.as_ref(),
        candidate.method.as_ref(),
        violations,
    );
    if previous.supports_subscriptions && !candidate.supports_subscriptions {
        violations.push(CompatibilityViolation::ResourceSubscriptionsDisabled {
            capability_id: capability_id.to_owned(),
        });
    }
}

fn compare_function(
    capability_id: &str,
    previous: &reframe_store_protocol::package::Function,
    candidate: &reframe_store_protocol::package::Function,
    violations: &mut Vec<CompatibilityViolation>,
) {
    compare_type(
        capability_id,
        "input",
        &previous.input_type,
        &candidate.input_type,
        violations,
    );
    compare_type(
        capability_id,
        "output",
        &previous.output_type,
        &candidate.output_type,
        violations,
    );
    compare_binding(
        capability_id,
        previous.method.as_ref(),
        candidate.method.as_ref(),
        violations,
    );
    if previous.side_effect != candidate.side_effect {
        violations.push(CompatibilityViolation::FunctionSideEffectChanged {
            capability_id: capability_id.to_owned(),
            previous: previous.side_effect,
            candidate: candidate.side_effect,
        });
    }
    if previous.idempotency != candidate.idempotency {
        violations.push(CompatibilityViolation::FunctionIdempotencyChanged {
            capability_id: capability_id.to_owned(),
            previous: previous.idempotency,
            candidate: candidate.idempotency,
        });
    }
}

fn compare_type(
    capability_id: &str,
    role: &'static str,
    previous: &str,
    candidate: &str,
    violations: &mut Vec<CompatibilityViolation>,
) {
    if previous != candidate {
        violations.push(CompatibilityViolation::CapabilityContractTypeChanged {
            capability_id: capability_id.to_owned(),
            role,
            previous: previous.to_owned(),
            candidate: candidate.to_owned(),
        });
    }
}

fn compare_binding(
    capability_id: &str,
    previous: Option<&reframe_store_protocol::package::MethodBinding>,
    candidate: Option<&reframe_store_protocol::package::MethodBinding>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    if previous != candidate {
        violations.push(CompatibilityViolation::CapabilityMethodBindingChanged {
            capability_id: capability_id.to_owned(),
            previous: binding_name(previous),
            candidate: binding_name(candidate),
        });
    }
}

fn binding_name(binding: Option<&reframe_store_protocol::package::MethodBinding>) -> String {
    binding.map_or_else(
        || "<unbound>".to_owned(),
        |binding| format!("{}.{}", binding.service, binding.method),
    )
}

fn kind_name(entry: &CatalogEntry) -> &'static str {
    match entry.kind {
        Some(catalog_entry::Kind::Topic(_)) => "topic",
        Some(catalog_entry::Kind::Resource(_)) => "resource",
        Some(catalog_entry::Kind::Function(_)) => "function",
        Some(catalog_entry::Kind::Workflow(_)) => "workflow",
        None => "unspecified",
    }
}
