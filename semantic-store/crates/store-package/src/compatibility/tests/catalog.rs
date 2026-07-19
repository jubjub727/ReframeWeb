use reframe_store_protocol::package::{Idempotency, SideEffect};

use super::{
    super::CompatibilityViolation,
    catalog_fixture::{catalog, function_entry, resource_entry, topic_entry, violations},
};

#[test]
fn additive_catalog_metadata_and_features_are_compatible() {
    let previous = catalog(vec![resource_entry(
        "records.read",
        "compat.Selector",
        "compat.Value",
        false,
        "Read",
    )]);
    let mut resource = resource_entry(
        "records.read",
        "compat.Selector",
        "compat.Value",
        true,
        "Read",
    );
    resource.title = "Improved title".to_owned();
    let candidate = catalog(vec![resource, topic_entry("records")]);

    assert!(violations(&previous, &candidate).is_empty());
}

#[test]
fn removed_ids_and_kind_changes_are_stably_ordered() {
    let previous = catalog(vec![
        resource_entry("z.read", "compat.Selector", "compat.Value", false, "Read"),
        topic_entry("a.topic"),
    ]);
    let candidate = catalog(vec![function_entry(
        "z.read",
        "compat.Input",
        "compat.Output",
        SideEffect::None,
        Idempotency::Idempotent,
        "Call",
    )]);

    assert_eq!(
        violations(&previous, &candidate),
        vec![
            CompatibilityViolation::CapabilityRemoved {
                capability_id: "a.topic".to_owned(),
            },
            CompatibilityViolation::CapabilityKindChanged {
                capability_id: "z.read".to_owned(),
                previous: "resource".to_owned(),
                candidate: "function".to_owned(),
            },
        ]
    );
}

#[test]
fn stable_resource_contract_cannot_be_rebound_or_narrowed() {
    let previous = catalog(vec![resource_entry(
        "records.read",
        "compat.Selector",
        "compat.Value",
        true,
        "Read",
    )]);
    let candidate = catalog(vec![resource_entry(
        "records.read",
        "compat.OtherSelector",
        "compat.OtherValue",
        false,
        "Fetch",
    )]);

    let actual = violations(&previous, &candidate);
    assert_eq!(actual.len(), 4);
    assert!(matches!(
        actual[0],
        CompatibilityViolation::CapabilityContractTypeChanged {
            role: "selector",
            ..
        }
    ));
    assert!(matches!(
        actual[1],
        CompatibilityViolation::CapabilityContractTypeChanged { role: "value", .. }
    ));
    assert!(matches!(
        actual[2],
        CompatibilityViolation::CapabilityMethodBindingChanged { .. }
    ));
    assert!(matches!(
        actual[3],
        CompatibilityViolation::ResourceSubscriptionsDisabled { .. }
    ));
}

#[test]
fn stable_function_contract_classifications_cannot_change() {
    let previous = catalog(vec![function_entry(
        "records.update",
        "compat.Input",
        "compat.Output",
        SideEffect::WritesExternalState,
        Idempotency::IdempotentWithKey,
        "Update",
    )]);
    let candidate = catalog(vec![function_entry(
        "records.update",
        "compat.OtherInput",
        "compat.OtherOutput",
        SideEffect::Destructive,
        Idempotency::NotIdempotent,
        "Replace",
    )]);

    let actual = violations(&previous, &candidate);
    assert_eq!(actual.len(), 5);
    assert!(matches!(
        actual[0],
        CompatibilityViolation::CapabilityContractTypeChanged { role: "input", .. }
    ));
    assert!(matches!(
        actual[1],
        CompatibilityViolation::CapabilityContractTypeChanged { role: "output", .. }
    ));
    assert!(matches!(
        actual[2],
        CompatibilityViolation::CapabilityMethodBindingChanged { .. }
    ));
    assert!(matches!(
        actual[3],
        CompatibilityViolation::FunctionSideEffectChanged { .. }
    ));
    assert!(matches!(
        actual[4],
        CompatibilityViolation::FunctionIdempotencyChanged { .. }
    ));
}
