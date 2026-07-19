mod support;

use prost_types::Any;
use reframe_store_catalog::{CatalogError, InvocationMode};
use reframe_store_protocol::package::{CapabilityKind, catalog_entry};

use support::{HIT_TYPE, empty_any, hit_any, sample_catalog, service, service_from_catalog};

#[test]
fn resource_and_function_inputs_produce_typed_contracts() {
    let service = service();
    let read = service
        .validate_read("events.list", &empty_any(), false)
        .expect("read contract");
    assert_eq!(read.capability_id(), "events.list");
    assert_eq!(read.kind(), CapabilityKind::Resource);
    assert_eq!(read.expected_output_type(), HIT_TYPE);
    assert_eq!(read.mode(), InvocationMode::Unary);

    let subscription = service
        .validate_read("events.list", &empty_any(), true)
        .expect("subscription contract");
    assert_eq!(subscription.mode(), InvocationMode::Subscription);

    let call = service
        .validate_call("events.create", &hit_any("input"))
        .expect("call contract");
    assert_eq!(call.kind(), CapabilityKind::Function);
    service
        .validate_output(&call, &hit_any("output"))
        .expect("typed output");
}

#[test]
fn any_type_urls_payloads_and_unknown_fields_are_strictly_validated() {
    let service = service();
    let mut wrong_type = hit_any("input");
    wrong_type.type_url = "type.googleapis.com/google.protobuf.Empty".to_owned();
    assert_eq!(
        service.validate_call("events.create", &wrong_type),
        Err(CatalogError::TypeMismatch {
            expected: HIT_TYPE.to_owned(),
            actual: "google.protobuf.Empty".to_owned(),
        })
    );

    let invalid_url = Any {
        type_url: HIT_TYPE.to_owned(),
        value: Vec::new(),
    };
    assert_eq!(
        service.validate_call("events.create", &invalid_url),
        Err(CatalogError::InvalidTypeUrl {
            type_url: HIT_TYPE.to_owned(),
        })
    );

    let malformed = Any {
        type_url: format!("type.googleapis.com/{HIT_TYPE}"),
        value: vec![0x80],
    };
    assert!(matches!(
        service.validate_call("events.create", &malformed),
        Err(CatalogError::InvalidPayload { .. })
    ));

    let mut unknown = hit_any("input");
    unknown.value.extend_from_slice(&[0xf8, 0x07, 0x01]);
    assert!(matches!(
        service.validate_call("events.create", &unknown),
        Err(CatalogError::InvalidPayload { reason, .. })
            if reason.contains("absent")
    ));
}

#[test]
fn reflective_decoding_has_a_structural_allocation_budget() {
    let service = service();
    let mut value = hit_any("ignored");
    value.value.clear();
    for _ in 0..20_000 {
        value.value.extend_from_slice(&[0x0a, 0x01, b'x']);
    }

    assert!(matches!(
        service.validate_call("events.create", &value),
        Err(CatalogError::InvalidPayload { reason, .. })
            if reason.contains("too many structural values")
    ));
}

#[test]
fn invocation_kind_and_subscription_contracts_are_enforced() {
    let service = service();
    assert!(matches!(
        service.validate_call("events.list", &hit_any("input")),
        Err(CatalogError::CapabilityKindMismatch {
            expected: "function",
            ..
        })
    ));

    let mut catalog = sample_catalog();
    let resource = catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "events.list")
        .expect("resource");
    let Some(catalog_entry::Kind::Resource(resource)) = resource.kind.as_mut() else {
        panic!("resource kind");
    };
    resource.supports_subscriptions = false;
    let service = service_from_catalog(catalog);
    assert_eq!(
        service.validate_read("events.list", &empty_any(), true),
        Err(CatalogError::SubscriptionsUnsupported {
            capability_id: "events.list".to_owned(),
        })
    );
}
