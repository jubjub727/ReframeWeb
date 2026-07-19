use std::collections::HashSet;

use prost_reflect::{DescriptorPool, MethodDescriptor};
use reframe_store_protocol::{
    annotations::{
        CAPABILITY_OPTION_FULL_NAME, Capability, Idempotency as AnnotatedIdempotency,
        STORE_SERVICE_OPTION_FULL_NAME, SideEffect as AnnotatedSideEffect, StoreService,
        capability,
    },
    package::{
        CatalogEntry, ErrorCase, Function, Guidance, Idempotency, MethodBinding, Resource,
        SideEffect, catalog_entry,
    },
};

use crate::CatalogError;

pub(super) fn capabilities(
    pool: &DescriptorPool,
    store_id: &str,
) -> Result<Option<Vec<CatalogEntry>>, CatalogError> {
    let Some(capability_extension) = pool.get_extension_by_name(CAPABILITY_OPTION_FULL_NAME) else {
        return Ok(None);
    };
    let store_extension = pool
        .get_extension_by_name(STORE_SERVICE_OPTION_FULL_NAME)
        .ok_or(CatalogError::MissingCapabilityExtension)?;
    let mut entries = Vec::new();
    let mut ids = HashSet::new();
    let mut matching_services = 0_usize;
    for service in pool.services() {
        let service_options = service.options();
        if !service_options.has_extension(&store_extension) {
            continue;
        }
        let value = service_options.get_extension(&store_extension);
        let marker = value
            .as_message()
            .ok_or_else(|| invalid_store_option(service.full_name(), "option is not a message"))?
            .transcode_to::<StoreService>()
            .map_err(|error| invalid_store_option(service.full_name(), &error.to_string()))?;
        reframe_store_protocol::validate_store_id(&marker.store_id)
            .map_err(|error| invalid_store_option(service.full_name(), &error.to_string()))?;
        if marker.store_id != store_id {
            continue;
        }
        matching_services += 1;
        for method in service.methods() {
            let options = method.options();
            if !options.has_extension(&capability_extension) {
                return Err(CatalogError::MissingMethodCapabilityAnnotation {
                    method: method.full_name().to_owned(),
                });
            }
            let value = options.get_extension(&capability_extension);
            let annotation = value
                .as_message()
                .ok_or_else(|| invalid_option(&method, "option is not a message"))?
                .transcode_to::<Capability>()
                .map_err(|error| invalid_option(&method, &error.to_string()))?;
            if !ids.insert(annotation.id.clone()) {
                return Err(CatalogError::DuplicateEntry {
                    entry_id: annotation.id,
                });
            }
            entries.push(to_entry(annotation, &method)?);
        }
    }
    if matching_services == 0 {
        return Err(CatalogError::MissingAnnotatedStoreService {
            store_id: store_id.to_owned(),
        });
    }
    if entries.is_empty() {
        return Err(CatalogError::MissingAnnotatedCapabilities {
            store_id: store_id.to_owned(),
        });
    }
    Ok(Some(entries))
}

fn to_entry(
    mut annotation: Capability,
    method: &MethodDescriptor,
) -> Result<CatalogEntry, CatalogError> {
    if method.is_client_streaming() || method.is_server_streaming() {
        return Err(CatalogError::StreamingMethodBinding {
            entry_id: annotation.id,
            service: method.parent_service().full_name().to_owned(),
            method: method.name().to_owned(),
        });
    }
    let kind = annotation
        .kind
        .take()
        .ok_or_else(|| CatalogError::MissingCapabilityKind {
            method: method.full_name().to_owned(),
        })?;
    let entry_kind = match kind {
        capability::Kind::Resource(resource) => catalog_entry::Kind::Resource(Resource {
            selector_type: method.input().full_name().to_owned(),
            value_type: method.output().full_name().to_owned(),
            supports_subscriptions: resource.supports_subscriptions,
            method: Some(binding(method)),
        }),
        capability::Kind::Function(function) => catalog_entry::Kind::Function(Function {
            input_type: method.input().full_name().to_owned(),
            output_type: method.output().full_name().to_owned(),
            side_effect: map_side_effect(function.side_effect, &annotation.id)?,
            idempotency: map_idempotency(function.idempotency, &annotation.id)?,
            method: Some(binding(method)),
        }),
    };
    Ok(CatalogEntry {
        id: annotation.id,
        parent_topic_id: annotation.parent_topic_id,
        title: annotation.title,
        summary: annotation.summary,
        intent_phrases: annotation.intent_phrases,
        related_entry_ids: annotation.related_entry_ids,
        guidance: annotation.guidance.map(|guidance| Guidance {
            when_to_use: guidance.when_to_use,
            when_not_to_use: guidance.when_not_to_use,
            errors: guidance
                .errors
                .into_iter()
                .map(|error| ErrorCase {
                    code: error.code,
                    summary: error.summary,
                    recovery: error.recovery,
                })
                .collect(),
            examples: Vec::new(),
        }),
        kind: Some(entry_kind),
    })
}

fn binding(method: &MethodDescriptor) -> MethodBinding {
    MethodBinding {
        service: method.parent_service().full_name().to_owned(),
        method: method.name().to_owned(),
    }
}

fn map_side_effect(value: i32, entry_id: &str) -> Result<i32, CatalogError> {
    let mapped = match AnnotatedSideEffect::try_from(value).ok() {
        Some(AnnotatedSideEffect::None) => SideEffect::None,
        Some(AnnotatedSideEffect::ReadsExternalState) => SideEffect::ReadsExternalState,
        Some(AnnotatedSideEffect::WritesExternalState) => SideEffect::WritesExternalState,
        Some(AnnotatedSideEffect::Destructive) => SideEffect::Destructive,
        Some(AnnotatedSideEffect::Unspecified) | None => {
            return Err(incomplete_function(entry_id));
        }
    };
    Ok(mapped as i32)
}

fn map_idempotency(value: i32, entry_id: &str) -> Result<i32, CatalogError> {
    let mapped = match AnnotatedIdempotency::try_from(value).ok() {
        Some(AnnotatedIdempotency::NotIdempotent) => Idempotency::NotIdempotent,
        Some(AnnotatedIdempotency::Idempotent) => Idempotency::Idempotent,
        Some(AnnotatedIdempotency::IdempotentWithKey) => Idempotency::IdempotentWithKey,
        Some(AnnotatedIdempotency::Unspecified) | None => {
            return Err(incomplete_function(entry_id));
        }
    };
    Ok(mapped as i32)
}

fn incomplete_function(entry_id: &str) -> CatalogError {
    CatalogError::IncompleteFunctionMetadata {
        entry_id: entry_id.to_owned(),
    }
}

fn invalid_option(method: &MethodDescriptor, reason: &str) -> CatalogError {
    CatalogError::InvalidCapabilityAnnotation {
        method: method.full_name().to_owned(),
        reason: reason.to_owned(),
    }
}

fn invalid_store_option(service: &str, reason: &str) -> CatalogError {
    CatalogError::InvalidStoreServiceAnnotation {
        service: service.to_owned(),
        reason: reason.to_owned(),
    }
}
