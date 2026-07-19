use prost_reflect::{
    Cardinality as DescriptorCardinality, EnumDescriptor, FieldDescriptor, Kind, MessageDescriptor,
};
use reframe_store_protocol::wire::{
    Cardinality, EnumValueView, FieldKind, FieldView, TypeKind, TypeView,
};

use crate::{
    budget::ProjectionBudget,
    field_selection::{Selection, selected_field},
};

pub(crate) fn project_message(
    descriptor: &MessageDescriptor,
    selection: &Selection,
    depth: usize,
    budget: &mut ProjectionBudget,
) -> TypeView {
    project_message_inner(descriptor, selection, depth, &mut Vec::new(), budget)
}

pub(crate) fn project_enum(descriptor: &EnumDescriptor, budget: &mut ProjectionBudget) -> TypeView {
    let mut view = TypeView {
        full_name: descriptor.full_name().to_owned(),
        kind: TypeKind::Enum as i32,
        ..Default::default()
    };
    if !budget.claim(&view) {
        view.truncated = true;
        return view;
    }
    for value in descriptor.values() {
        let value = EnumValueView {
            name: value.name().to_owned(),
            number: value.number(),
        };
        if !budget.claim(&value) {
            view.truncated = true;
            break;
        }
        view.enum_values.push(value);
    }
    view
}

fn project_message_inner(
    descriptor: &MessageDescriptor,
    selection: &Selection,
    depth: usize,
    active: &mut Vec<String>,
    budget: &mut ProjectionBudget,
) -> TypeView {
    active.push(descriptor.full_name().to_owned());
    let mut view = TypeView {
        full_name: descriptor.full_name().to_owned(),
        kind: TypeKind::Message as i32,
        ..Default::default()
    };
    if !budget.claim(&view) {
        view.truncated = true;
        active.pop();
        return view;
    }

    let mut expansions = Vec::new();
    for field in descriptor.fields() {
        let Some(child_selection) = selected_field(selection, field.name()) else {
            continue;
        };
        let mut field_view = project_field(&field);
        let mut expansion = None;
        match field.kind() {
            Kind::Message(nested) => {
                let recursive = active.iter().any(|name| name == nested.full_name());
                if recursive {
                    field_view.recursive = true;
                    view.recursive = true;
                }
                if recursive && child_selection.is_all() {
                    // An unrestricted recursive edge is represented, not expanded.
                } else if depth > 1 {
                    expansion = Some(Kind::Message(nested));
                } else {
                    field_view.truncated = true;
                    view.truncated = true;
                }
            }
            Kind::Enum(enumeration) => {
                if depth > 1 {
                    expansion = Some(Kind::Enum(enumeration));
                } else {
                    field_view.truncated = true;
                    view.truncated = true;
                }
            }
            _ => {}
        }
        if !budget.claim(&field_view) {
            view.truncated = true;
            break;
        }
        let field_index = view.fields.len();
        view.fields.push(field_view);
        if let Some(kind) = expansion {
            expansions.push(Expansion {
                field_index,
                kind,
                selection: child_selection,
            });
        }
    }

    // Expand only after the shallow field list has been charged. This keeps
    // useful breadth and prevents the first edge into a shared wide type from
    // consuming the entire budget before sibling fields are represented.
    for expansion in expansions {
        let field = &mut view.fields[expansion.field_index];
        if budget.exhausted() {
            field.truncated = true;
            view.truncated = true;
            continue;
        }
        let nested = match expansion.kind {
            Kind::Message(descriptor) => {
                project_message_inner(&descriptor, expansion.selection, depth - 1, active, budget)
            }
            Kind::Enum(descriptor) => project_enum(&descriptor, budget),
            _ => unreachable!("only message and enum fields require expansion"),
        };
        field.truncated |= nested.truncated;
        view.recursive |= nested.recursive;
        view.truncated |= nested.truncated;
        field.nested = Some(nested);
    }
    active.pop();
    view
}

struct Expansion<'a> {
    field_index: usize,
    kind: Kind,
    selection: &'a Selection,
}

fn project_field(field: &FieldDescriptor) -> FieldView {
    let (type_name, kind) = match field.kind() {
        Kind::Message(message) => (map_or_message_name(field, &message), FieldKind::Message),
        Kind::Enum(enumeration) => (enumeration.full_name().to_owned(), FieldKind::Enum),
        scalar => (scalar_name(&scalar).to_owned(), FieldKind::Scalar),
    };
    FieldView {
        name: field.name().to_owned(),
        number: field.number(),
        type_name,
        cardinality: match field.cardinality() {
            DescriptorCardinality::Optional => Cardinality::Optional,
            DescriptorCardinality::Required => Cardinality::Required,
            DescriptorCardinality::Repeated => Cardinality::Repeated,
        } as i32,
        is_map: field.is_map(),
        nested: None,
        kind: kind as i32,
        oneof_name: field
            .containing_oneof()
            .filter(|oneof| !oneof.is_synthetic())
            .map(|oneof| oneof.name().to_owned())
            .unwrap_or_default(),
        supports_presence: field.supports_presence(),
        recursive: false,
        truncated: false,
    }
}

fn map_or_message_name(field: &FieldDescriptor, message: &MessageDescriptor) -> String {
    if !field.is_map() {
        return message.full_name().to_owned();
    }
    let key = message
        .get_field_by_name("key")
        .map(|field| field_type_name(&field))
        .unwrap_or_else(|| "?".to_owned());
    let value = message
        .get_field_by_name("value")
        .map(|field| field_type_name(&field))
        .unwrap_or_else(|| "?".to_owned());
    format!("map<{key}, {value}>")
}

fn field_type_name(field: &FieldDescriptor) -> String {
    match field.kind() {
        Kind::Message(message) => message.full_name().to_owned(),
        Kind::Enum(enumeration) => enumeration.full_name().to_owned(),
        scalar => scalar_name(&scalar).to_owned(),
    }
}

const fn scalar_name(kind: &Kind) -> &'static str {
    match kind {
        Kind::Double => "double",
        Kind::Float => "float",
        Kind::Int32 => "int32",
        Kind::Int64 => "int64",
        Kind::Uint32 => "uint32",
        Kind::Uint64 => "uint64",
        Kind::Sint32 => "sint32",
        Kind::Sint64 => "sint64",
        Kind::Fixed32 => "fixed32",
        Kind::Fixed64 => "fixed64",
        Kind::Sfixed32 => "sfixed32",
        Kind::Sfixed64 => "sfixed64",
        Kind::Bool => "bool",
        Kind::String => "string",
        Kind::Bytes => "bytes",
        Kind::Message(_) | Kind::Enum(_) => "",
    }
}
