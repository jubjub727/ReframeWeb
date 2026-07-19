use reframe_store_protocol::package::{
    Catalog, CatalogEntry, Function, Idempotency, MethodBinding, Resource, SideEffect, Topic,
    catalog_entry,
};

use super::super::{CompatibilityViolation, catalog::compare_catalog};

pub(super) fn violations(previous: &Catalog, candidate: &Catalog) -> Vec<CompatibilityViolation> {
    let mut violations = Vec::new();
    compare_catalog(previous, candidate, &mut violations);
    violations
}

pub(super) fn catalog(entries: Vec<CatalogEntry>) -> Catalog {
    Catalog {
        entries,
        ..Catalog::default()
    }
}

pub(super) fn topic_entry(id: &str) -> CatalogEntry {
    entry(id, catalog_entry::Kind::Topic(Topic {}))
}

pub(super) fn resource_entry(
    id: &str,
    selector_type: &str,
    value_type: &str,
    supports_subscriptions: bool,
    method: &str,
) -> CatalogEntry {
    entry(
        id,
        catalog_entry::Kind::Resource(Resource {
            selector_type: selector_type.to_owned(),
            value_type: value_type.to_owned(),
            supports_subscriptions,
            method: Some(binding(method)),
        }),
    )
}

pub(super) fn function_entry(
    id: &str,
    input_type: &str,
    output_type: &str,
    side_effect: SideEffect,
    idempotency: Idempotency,
    method: &str,
) -> CatalogEntry {
    entry(
        id,
        catalog_entry::Kind::Function(Function {
            input_type: input_type.to_owned(),
            output_type: output_type.to_owned(),
            side_effect: side_effect as i32,
            idempotency: idempotency as i32,
            method: Some(binding(method)),
        }),
    )
}

fn entry(id: &str, kind: catalog_entry::Kind) -> CatalogEntry {
    CatalogEntry {
        id: id.to_owned(),
        kind: Some(kind),
        ..CatalogEntry::default()
    }
}

fn binding(method: &str) -> MethodBinding {
    MethodBinding {
        service: "compat.Api".to_owned(),
        method: method.to_owned(),
    }
}
