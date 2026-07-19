use prost_types::{
    MessageOptions, OneofDescriptorProto,
    descriptor_proto::ReservedRange,
    field_descriptor_proto::{Label, Type},
};

use super::super::{
    CompatibilityViolation, compare_descriptor_sets,
    test_schema::{field, message, schema},
};

#[test]
fn removed_fields_require_reserved_names_and_numbers() {
    let previous = schema(
        vec![message(
            "Record",
            [
                field("keep", 1, Type::Int32, Label::Optional),
                field("retired", 2, Type::Int32, Label::Optional),
                field("number_only", 3, Type::Int32, Label::Optional),
                field("name_only", 4, Type::Int32, Label::Optional),
            ],
        )],
        vec![],
        vec![],
    );
    let mut candidate_message = message("Record", [field("keep", 1, Type::Int32, Label::Optional)]);
    candidate_message.reserved_range.push(ReservedRange {
        start: Some(2),
        end: Some(4),
    });
    candidate_message.reserved_name = vec!["retired".to_owned(), "name_only".to_owned()];
    let candidate = schema(vec![candidate_message], vec![], vec![]);

    assert_eq!(
        violations(&previous, &candidate),
        vec![
            CompatibilityViolation::FieldRemovedWithoutReservation {
                message: "compat.Record".to_owned(),
                field: "number_only".to_owned(),
                number: 3,
                number_reserved: true,
                name_reserved: false,
            },
            CompatibilityViolation::FieldRemovedWithoutReservation {
                message: "compat.Record".to_owned(),
                field: "name_only".to_owned(),
                number: 4,
                number_reserved: false,
                name_reserved: true,
            },
        ]
    );
}

#[test]
fn field_reservations_remain_monotonic_across_releases() {
    let mut previous_message = message("Record", [field("keep", 1, Type::Int32, Label::Optional)]);
    previous_message.reserved_range.push(ReservedRange {
        start: Some(2),
        end: Some(5),
    });
    previous_message.reserved_name = vec!["retired".to_owned()];

    let mut candidate_message = message("Record", [field("keep", 1, Type::Int32, Label::Optional)]);
    candidate_message.reserved_range.push(ReservedRange {
        start: Some(2),
        end: Some(4),
    });
    let actual = violations(
        &schema(vec![previous_message], vec![], vec![]),
        &schema(vec![candidate_message], vec![], vec![]),
    );
    assert_eq!(
        actual,
        vec![
            CompatibilityViolation::FieldNumberReservationRemoved {
                message: "compat.Record".to_owned(),
                start: 2,
                end: 5,
            },
            CompatibilityViolation::FieldNameReservationRemoved {
                message: "compat.Record".to_owned(),
                name: "retired".to_owned(),
            },
        ]
    );
}

#[test]
fn field_shape_changes_are_breaking() {
    let mut previous_message = message(
        "Record",
        [
            field("moved", 1, Type::Int32, Label::Optional),
            field("renamed", 2, Type::Int32, Label::Optional),
            field("typed", 3, Type::Int32, Label::Optional),
            field("many", 4, Type::Int32, Label::Optional),
            field("choice", 5, Type::Int32, Label::Optional),
            field("presence", 6, Type::Int32, Label::Optional),
        ],
    );
    previous_message.oneof_decl.push(oneof("old_choice"));
    previous_message.field[4].oneof_index = Some(0);

    let mut candidate_message = message(
        "Record",
        [
            field("moved", 10, Type::Int32, Label::Optional),
            field("new_name", 2, Type::Int32, Label::Optional),
            field("typed", 3, Type::String, Label::Optional),
            field("many", 4, Type::Int32, Label::Repeated),
            field("choice", 5, Type::Int32, Label::Optional),
            field("presence", 6, Type::Int32, Label::Optional),
            field("required", 7, Type::Int32, Label::Required),
        ],
    );
    candidate_message.oneof_decl.push(oneof("new_choice"));
    candidate_message.field[4].oneof_index = Some(0);
    candidate_message.field[5].proto3_optional = Some(true);

    let actual = violations(
        &schema(vec![previous_message], vec![], vec![]),
        &schema(vec![candidate_message], vec![], vec![]),
    );
    assert_eq!(actual.len(), 7);
    assert!(matches!(
        actual[0],
        CompatibilityViolation::FieldNumberChanged { .. }
    ));
    assert!(matches!(
        actual[1],
        CompatibilityViolation::FieldNameChanged { .. }
    ));
    assert!(matches!(
        actual[2],
        CompatibilityViolation::FieldTypeChanged { .. }
    ));
    assert!(matches!(
        actual[3],
        CompatibilityViolation::FieldCardinalityChanged { .. }
    ));
    assert!(matches!(
        actual[4],
        CompatibilityViolation::FieldOneofChanged { .. }
    ));
    assert!(matches!(
        actual[5],
        CompatibilityViolation::FieldPresenceChanged { .. }
    ));
    assert!(matches!(
        actual[6],
        CompatibilityViolation::RequiredFieldAdded { .. }
    ));
}

#[test]
fn map_entry_and_proto2_default_changes_are_breaking() {
    let mut previous_entry = message(
        "LabelsEntry",
        [
            field("key", 1, Type::String, Label::Optional),
            field("value", 2, Type::String, Label::Optional),
        ],
    );
    previous_entry.options = Some(MessageOptions {
        map_entry: Some(true),
        ..MessageOptions::default()
    });
    let mut candidate_entry = previous_entry.clone();
    candidate_entry.options = Some(MessageOptions {
        map_entry: Some(false),
        ..MessageOptions::default()
    });

    let mut previous_record = message(
        "Record",
        [
            field("count", 1, Type::Int32, Label::Optional),
            field("labels", 2, Type::Message, Label::Repeated),
        ],
    );
    previous_record.field[0].default_value = Some("7".to_owned());
    previous_record.field[1].type_name = Some(".compat.Record.LabelsEntry".to_owned());
    previous_record.nested_type.push(previous_entry);
    let mut candidate_record = previous_record.clone();
    candidate_record.field[0].default_value = Some("8".to_owned());
    candidate_record.nested_type[0] = candidate_entry;

    let mut previous = schema(vec![previous_record], vec![], vec![]);
    let mut candidate = schema(vec![candidate_record], vec![], vec![]);
    previous.file[0].syntax = Some("proto2".to_owned());
    candidate.file[0].syntax = Some("proto2".to_owned());

    assert_eq!(
        violations(&previous, &candidate),
        vec![
            CompatibilityViolation::FieldDefaultChanged {
                message: "compat.Record".to_owned(),
                field: "count".to_owned(),
                previous: Some("7".to_owned()),
                candidate: Some("8".to_owned()),
            },
            CompatibilityViolation::MessageMapEntryChanged {
                message: "compat.Record.LabelsEntry".to_owned(),
                previous: true,
                candidate: false,
            },
        ]
    );
}

fn violations(
    previous: &prost_types::FileDescriptorSet,
    candidate: &prost_types::FileDescriptorSet,
) -> Vec<CompatibilityViolation> {
    compare_descriptor_sets(previous, candidate).into_violations()
}

fn oneof(name: &str) -> OneofDescriptorProto {
    OneofDescriptorProto {
        name: Some(name.to_owned()),
        ..OneofDescriptorProto::default()
    }
}
