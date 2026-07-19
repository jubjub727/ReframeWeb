use std::collections::HashSet;

use prost_reflect::{DescriptorPool, DynamicMessage, MessageDescriptor, MethodDescriptor};
use prost_types::Any;
use reframe_store_protocol::{
    MAX_TYPE_NAME_BYTES, MAX_TYPE_URL_BYTES,
    package::{CatalogEntry, Idempotency, MethodBinding, SideEffect, catalog_entry},
};

use super::{CatalogError, EntryMap, invalid_entry, missing_relation};

const MAX_WORKFLOW_STEPS: usize = 32;
const CANONICAL_TYPE_URL_PREFIX: &str = "type.googleapis.com/";

pub(super) fn validate(entries: &EntryMap<'_>, pool: &DescriptorPool) -> Result<(), CatalogError> {
    let mut bindings = HashSet::new();
    for entry in entries.values() {
        match entry.kind.as_ref().expect("kinds validated") {
            catalog_entry::Kind::Resource(resource) => {
                let method = validate_method(entry, resource.method.as_ref(), pool, &mut bindings)?;
                validate_declared_type(entry, "input", &resource.selector_type, &method.input())?;
                validate_declared_type(entry, "output", &resource.value_type, &method.output())?;
                validate_examples(entry, Some(method.input()), Some(method.output()), pool)?;
            }
            catalog_entry::Kind::Function(function) => {
                if function.side_effect == SideEffect::Unspecified as i32
                    || function.idempotency == Idempotency::Unspecified as i32
                {
                    return Err(CatalogError::IncompleteFunctionMetadata {
                        entry_id: entry.id.clone(),
                    });
                }
                let method = validate_method(entry, function.method.as_ref(), pool, &mut bindings)?;
                validate_declared_type(entry, "input", &function.input_type, &method.input())?;
                validate_declared_type(entry, "output", &function.output_type, &method.output())?;
                validate_examples(entry, Some(method.input()), Some(method.output()), pool)?;
            }
            catalog_entry::Kind::Workflow(workflow) => {
                validate_workflow(entry, workflow, entries)?;
                validate_examples(entry, None, None, pool)?;
            }
            catalog_entry::Kind::Topic(_) => {}
        }
    }
    Ok(())
}

fn validate_workflow(
    entry: &CatalogEntry,
    workflow: &reframe_store_protocol::package::Workflow,
    entries: &EntryMap<'_>,
) -> Result<(), CatalogError> {
    if workflow.steps.is_empty() {
        return Err(CatalogError::EmptyWorkflow {
            entry_id: entry.id.clone(),
        });
    }
    if workflow.steps.len() > MAX_WORKFLOW_STEPS {
        return Err(CatalogError::MetadataLimit {
            entry_id: entry.id.clone(),
            field: "workflow.steps",
            limit: MAX_WORKFLOW_STEPS,
        });
    }
    for step in &workflow.steps {
        if step.instruction.trim().is_empty()
            || step.instruction.len() > 1_024
            || step.condition.len() > 512
            || step.capability_id == entry.id
        {
            return Err(invalid_entry(entry, "workflow.steps"));
        }
        if !entries.contains_key(step.capability_id.as_str()) {
            return Err(missing_relation(
                entry,
                "workflow capability",
                &step.capability_id,
            ));
        }
    }
    Ok(())
}

fn validate_method(
    entry: &CatalogEntry,
    binding: Option<&MethodBinding>,
    pool: &DescriptorPool,
    bindings: &mut HashSet<(String, String)>,
) -> Result<MethodDescriptor, CatalogError> {
    let Some(binding) = binding else {
        return Err(CatalogError::InvalidMethodBinding {
            entry_id: entry.id.clone(),
        });
    };
    let service_name = binding.service.trim_start_matches('.');
    if service_name.is_empty() || binding.method.is_empty() {
        return Err(CatalogError::InvalidMethodBinding {
            entry_id: entry.id.clone(),
        });
    }
    let Some(service) = pool.get_service_by_name(service_name) else {
        return Err(CatalogError::ServiceNotFound {
            entry_id: entry.id.clone(),
            service: binding.service.clone(),
        });
    };
    let Some(method) = service
        .methods()
        .find(|method| method.name() == binding.method)
    else {
        return Err(CatalogError::MethodNotFound {
            entry_id: entry.id.clone(),
            service: binding.service.clone(),
            method: binding.method.clone(),
        });
    };
    if method.is_client_streaming() || method.is_server_streaming() {
        return Err(CatalogError::StreamingMethodBinding {
            entry_id: entry.id.clone(),
            service: binding.service.clone(),
            method: binding.method.clone(),
        });
    }
    if !bindings.insert((service_name.to_owned(), binding.method.clone())) {
        return Err(CatalogError::DuplicateMethodBinding {
            service: binding.service.clone(),
            method: binding.method.clone(),
        });
    }
    Ok(method)
}

fn validate_declared_type(
    entry: &CatalogEntry,
    direction: &'static str,
    declared: &str,
    actual: &MessageDescriptor,
) -> Result<(), CatalogError> {
    let canonical = declared.trim_start_matches('.');
    if !declared_type_fits_wire(declared, canonical) {
        return Err(invalid_entry(entry, "declared protobuf type name"));
    }
    if canonical != actual.full_name() {
        return Err(CatalogError::MethodTypeMismatch {
            entry_id: entry.id.clone(),
            direction,
            declared: declared.to_owned(),
            actual: actual.full_name().to_owned(),
        });
    }
    Ok(())
}

fn declared_type_fits_wire(declared: &str, canonical: &str) -> bool {
    declared.len() <= MAX_TYPE_NAME_BYTES
        && CANONICAL_TYPE_URL_PREFIX
            .len()
            .saturating_add(canonical.len())
            <= MAX_TYPE_URL_BYTES
}

fn validate_examples(
    entry: &CatalogEntry,
    input: Option<MessageDescriptor>,
    output: Option<MessageDescriptor>,
    pool: &DescriptorPool,
) -> Result<(), CatalogError> {
    let examples = &entry
        .guidance
        .as_ref()
        .expect("guidance validated")
        .examples;
    for (index, example) in examples.iter().enumerate() {
        validate_example_value(
            entry,
            index,
            "input",
            example.input.as_ref(),
            input.clone(),
            pool,
        )?;
        validate_example_value(
            entry,
            index,
            "output",
            example.output.as_ref(),
            output.clone(),
            pool,
        )?;
    }
    Ok(())
}

fn validate_example_value(
    entry: &CatalogEntry,
    index: usize,
    direction: &'static str,
    value: Option<&Any>,
    expected: Option<MessageDescriptor>,
    pool: &DescriptorPool,
) -> Result<(), CatalogError> {
    let value = value.ok_or_else(|| CatalogError::MissingExampleValue {
        entry_id: entry.id.clone(),
        index,
        direction,
    })?;
    let type_name = value.type_url.rsplit('/').next().unwrap_or_default();
    let descriptor = if let Some(expected) = expected {
        if type_name != expected.full_name() {
            return Err(CatalogError::ExampleTypeMismatch {
                entry_id: entry.id.clone(),
                index,
                direction,
                expected: expected.full_name().to_owned(),
                actual: type_name.to_owned(),
            });
        }
        expected
    } else {
        pool.get_message_by_name(type_name)
            .ok_or_else(|| CatalogError::UnknownExampleType {
                entry_id: entry.id.clone(),
                index,
                direction,
                type_name: type_name.to_owned(),
            })?
    };
    DynamicMessage::decode(descriptor, value.value.as_slice()).map_err(|_| {
        CatalogError::InvalidExamplePayload {
            entry_id: entry.id.clone(),
            index,
            direction,
        }
    })?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn declared_types_leave_room_for_the_canonical_any_prefix() {
        let maximum_name = "x".repeat(MAX_TYPE_URL_BYTES - CANONICAL_TYPE_URL_PREFIX.len());
        assert!(declared_type_fits_wire(&maximum_name, &maximum_name));

        let oversized = format!("{maximum_name}x");
        assert!(!declared_type_fits_wire(&oversized, &oversized));
    }
}
