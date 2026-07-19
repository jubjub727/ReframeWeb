use prost_types::field_descriptor_proto::{Label, Type};

use super::super::{
    CompatibilityViolation, compare_descriptor_sets,
    test_schema::{enumeration, field, message, method, schema, service},
};

#[test]
fn additive_schema_changes_are_compatible() {
    let previous = schema(
        vec![message(
            "Record",
            [field("id", 1, Type::Int32, Label::Optional)],
        )],
        vec![enumeration("Status", [("STATUS_UNSPECIFIED", 0)])],
        vec![service(
            "Api",
            [method("Get", ".compat.Record", ".compat.Record")],
        )],
    );
    let candidate = schema(
        vec![
            message(
                "Record",
                [
                    field("id", 1, Type::Int32, Label::Optional),
                    field("label", 2, Type::String, Label::Optional),
                ],
            ),
            message("Added", []),
        ],
        vec![enumeration(
            "Status",
            [("STATUS_UNSPECIFIED", 0), ("STATUS_READY", 1)],
        )],
        vec![service(
            "Api",
            [
                method("Get", ".compat.Record", ".compat.Record"),
                method("List", ".compat.Record", ".compat.Added"),
            ],
        )],
    );

    assert!(compare_descriptor_sets(&previous, &candidate).is_empty());
}

#[test]
fn removed_symbols_are_reported_in_stable_name_order() {
    let mut outer = message("Outer", []);
    outer.nested_type.push(message("Nested", []));
    let previous = schema(
        vec![message("Zulu", []), message("Alpha", []), outer],
        vec![enumeration("Status", [("STATUS_UNSPECIFIED", 0)])],
        vec![service(
            "Api",
            [method("Get", ".compat.Alpha", ".compat.Zulu")],
        )],
    );
    let candidate = schema(vec![message("Outer", [])], vec![], vec![]);

    assert_eq!(
        compare_descriptor_sets(&previous, &candidate).into_violations(),
        vec![
            CompatibilityViolation::MessageRemoved {
                message: "compat.Alpha".to_owned(),
            },
            CompatibilityViolation::MessageRemoved {
                message: "compat.Outer.Nested".to_owned(),
            },
            CompatibilityViolation::MessageRemoved {
                message: "compat.Zulu".to_owned(),
            },
            CompatibilityViolation::EnumRemoved {
                enumeration: "compat.Status".to_owned(),
            },
            CompatibilityViolation::ServiceRemoved {
                service: "compat.Api".to_owned(),
            },
        ]
    );
}
