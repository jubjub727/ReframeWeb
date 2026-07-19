use prost_types::enum_descriptor_proto::EnumReservedRange;

use super::super::{
    CompatibilityViolation, compare_descriptor_sets,
    test_schema::{enumeration, method, schema, service},
};

#[test]
fn enum_value_removals_require_both_reservations() {
    let previous = schema(
        vec![],
        vec![enumeration(
            "Status",
            [
                ("STATUS_UNSPECIFIED", 0),
                ("STATUS_RETIRED", 1),
                ("STATUS_NUMBER_ONLY", 2),
                ("STATUS_NAME_ONLY", 3),
                ("STATUS_MOVED", 4),
            ],
        )],
        vec![],
    );
    let mut candidate_enum =
        enumeration("Status", [("STATUS_UNSPECIFIED", 0), ("STATUS_MOVED", 8)]);
    candidate_enum.reserved_range = vec![enum_range(1), enum_range(2)];
    candidate_enum.reserved_name = vec!["STATUS_RETIRED".to_owned(), "STATUS_NAME_ONLY".to_owned()];
    let candidate = schema(vec![], vec![candidate_enum], vec![]);

    let actual = violations(&previous, &candidate);
    assert_eq!(actual.len(), 3);
    assert!(matches!(
        actual[0],
        CompatibilityViolation::EnumValueRemovedWithoutReservation {
            number_reserved: true,
            name_reserved: false,
            ..
        }
    ));
    assert!(matches!(
        actual[1],
        CompatibilityViolation::EnumValueRemovedWithoutReservation {
            number_reserved: false,
            name_reserved: true,
            ..
        }
    ));
    assert!(matches!(
        actual[2],
        CompatibilityViolation::EnumValueNumberChanged {
            previous: 4,
            candidate: 8,
            ..
        }
    ));
}

#[test]
fn enum_reservations_remain_monotonic_across_releases() {
    let mut previous_enum = enumeration("Status", [("STATUS_UNSPECIFIED", 0)]);
    previous_enum.reserved_range = vec![EnumReservedRange {
        start: Some(1),
        end: Some(3),
    }];
    previous_enum.reserved_name = vec!["STATUS_RETIRED".to_owned()];

    let mut candidate_enum = enumeration("Status", [("STATUS_UNSPECIFIED", 0)]);
    candidate_enum.reserved_range = vec![enum_range(1), enum_range(2)];
    let actual = violations(
        &schema(vec![], vec![previous_enum], vec![]),
        &schema(vec![], vec![candidate_enum], vec![]),
    );
    assert_eq!(
        actual,
        vec![
            CompatibilityViolation::EnumNumberReservationRemoved {
                enumeration: "compat.Status".to_owned(),
                start: 1,
                end: 3,
            },
            CompatibilityViolation::EnumNameReservationRemoved {
                enumeration: "compat.Status".to_owned(),
                name: "STATUS_RETIRED".to_owned(),
            },
        ]
    );
}

#[test]
fn rpc_contract_and_streaming_changes_are_breaking() {
    let previous = schema(
        vec![],
        vec![],
        vec![service(
            "Api",
            [
                method("Keep", ".compat.Request", ".compat.Response"),
                method("Remove", ".compat.Request", ".compat.Response"),
            ],
        )],
    );
    let mut changed = method("Keep", ".compat.OtherRequest", ".compat.OtherResponse");
    changed.client_streaming = Some(true);
    changed.server_streaming = Some(true);
    let candidate = schema(vec![], vec![], vec![service("Api", [changed])]);

    let actual = violations(&previous, &candidate);
    assert_eq!(actual.len(), 5);
    assert!(matches!(
        actual[0],
        CompatibilityViolation::RpcInputChanged { .. }
    ));
    assert!(matches!(
        actual[1],
        CompatibilityViolation::RpcOutputChanged { .. }
    ));
    assert!(matches!(
        actual[2],
        CompatibilityViolation::RpcClientStreamingChanged { .. }
    ));
    assert!(matches!(
        actual[3],
        CompatibilityViolation::RpcServerStreamingChanged { .. }
    ));
    assert!(matches!(
        actual[4],
        CompatibilityViolation::MethodRemoved { .. }
    ));
}

fn violations(
    previous: &prost_types::FileDescriptorSet,
    candidate: &prost_types::FileDescriptorSet,
) -> Vec<CompatibilityViolation> {
    compare_descriptor_sets(previous, candidate).into_violations()
}

fn enum_range(number: i32) -> EnumReservedRange {
    EnumReservedRange {
        start: Some(number),
        end: Some(number),
    }
}
