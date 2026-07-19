use prost_types::{
    DescriptorProto, FieldDescriptorProto,
    field_descriptor_proto::{Label, Type},
};

use super::violation::CompatibilityViolation;

pub(super) fn compare_shape(
    message: &str,
    previous_message: &DescriptorProto,
    candidate_message: &DescriptorProto,
    previous: &FieldDescriptorProto,
    candidate: &FieldDescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let field = previous.name.as_deref().unwrap_or_default();
    let previous_type = field_type(previous);
    let candidate_type = field_type(candidate);
    if previous_type != candidate_type {
        violations.push(CompatibilityViolation::FieldTypeChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: previous_type,
            candidate: candidate_type,
        });
    }
    let previous_cardinality = cardinality(previous);
    let candidate_cardinality = cardinality(candidate);
    if previous_cardinality != candidate_cardinality {
        violations.push(CompatibilityViolation::FieldCardinalityChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: previous_cardinality,
            candidate: candidate_cardinality,
        });
    }
    let previous_oneof = oneof_name(previous_message, previous);
    let candidate_oneof = oneof_name(candidate_message, candidate);
    if previous_oneof != candidate_oneof {
        violations.push(CompatibilityViolation::FieldOneofChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: previous_oneof,
            candidate: candidate_oneof,
        });
    }
    let previous_presence = previous.proto3_optional.unwrap_or(false);
    let candidate_presence = candidate.proto3_optional.unwrap_or(false);
    if previous_presence != candidate_presence {
        violations.push(CompatibilityViolation::FieldPresenceChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: previous_presence,
            candidate: candidate_presence,
        });
    }
    if previous.default_value != candidate.default_value {
        violations.push(CompatibilityViolation::FieldDefaultChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: previous.default_value.clone(),
            candidate: candidate.default_value.clone(),
        });
    }
}

fn oneof_name(message: &DescriptorProto, field: &FieldDescriptorProto) -> Option<String> {
    let index = usize::try_from(field.oneof_index?).ok()?;
    message.oneof_decl.get(index)?.name.clone()
}

fn cardinality(field: &FieldDescriptorProto) -> String {
    Label::try_from(field.label.unwrap_or(Label::Optional as i32)).map_or_else(
        |value| format!("unknown({value})"),
        |value| format!("{value:?}").to_lowercase(),
    )
}

fn field_type(field: &FieldDescriptorProto) -> String {
    let kind = Type::try_from(field.r#type.unwrap_or_default()).map_or_else(
        |value| format!("unknown({value})"),
        |value| format!("{value:?}").to_lowercase(),
    );
    match field.type_name.as_deref().filter(|name| !name.is_empty()) {
        Some(name) => format!("{kind} {name}"),
        None => kind,
    }
}
