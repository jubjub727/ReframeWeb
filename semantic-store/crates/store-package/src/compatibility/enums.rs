use std::collections::BTreeMap;

use super::{index::SchemaIndex, reservations, violation::CompatibilityViolation};

pub(super) fn compare_enums(
    previous: &SchemaIndex<'_>,
    candidate: &SchemaIndex<'_>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    for (name, previous_enum) in &previous.enums {
        let Some(candidate_enum) = candidate.enums.get(name) else {
            violations.push(CompatibilityViolation::EnumRemoved {
                enumeration: name.clone(),
            });
            continue;
        };
        let candidate_values = candidate_enum
            .value
            .iter()
            .filter_map(|value| Some((value.name.as_deref()?, value)))
            .collect::<BTreeMap<_, _>>();
        let mut previous_values = previous_enum.value.iter().collect::<Vec<_>>();
        previous_values.sort_unstable_by_key(|value| {
            (value.number.unwrap_or_default(), value.name.as_deref())
        });
        for previous_value in previous_values {
            let value = previous_value.name.as_deref().unwrap_or_default();
            let previous_number = previous_value.number.unwrap_or_default();
            let Some(candidate_value) = candidate_values.get(value) else {
                check_removed_value(name, value, previous_number, candidate_enum, violations);
                continue;
            };
            let candidate_number = candidate_value.number.unwrap_or_default();
            if previous_number != candidate_number {
                violations.push(CompatibilityViolation::EnumValueNumberChanged {
                    enumeration: name.clone(),
                    value: value.to_owned(),
                    previous: previous_number,
                    candidate: candidate_number,
                });
            }
        }
        compare_reservations(name, previous_enum, candidate_enum, violations);
    }
}

fn compare_reservations(
    enumeration: &str,
    previous: &prost_types::EnumDescriptorProto,
    candidate: &prost_types::EnumDescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let candidate_ranges = candidate
        .reserved_range
        .iter()
        .map(|range| {
            (
                i64::from(range.start.unwrap_or_default()),
                i64::from(range.end.unwrap_or_default()) + 1,
            )
        })
        .collect::<Vec<_>>();
    let mut previous_ranges = previous.reserved_range.iter().collect::<Vec<_>>();
    previous_ranges.sort_unstable_by_key(|range| {
        (
            range.start.unwrap_or_default(),
            range.end.unwrap_or_default(),
        )
    });
    for range in previous_ranges {
        let start = range.start.unwrap_or_default();
        let end = range.end.unwrap_or_default();
        if !reservations::covers(
            candidate_ranges.iter().copied(),
            i64::from(start),
            i64::from(end) + 1,
        ) {
            violations.push(CompatibilityViolation::EnumNumberReservationRemoved {
                enumeration: enumeration.to_owned(),
                start,
                end,
            });
        }
    }

    let candidate_names = candidate
        .reserved_name
        .iter()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();
    let previous_names = previous
        .reserved_name
        .iter()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();
    for name in previous_names.difference(&candidate_names) {
        violations.push(CompatibilityViolation::EnumNameReservationRemoved {
            enumeration: enumeration.to_owned(),
            name: (*name).to_owned(),
        });
    }
}

fn check_removed_value(
    enumeration: &str,
    value: &str,
    number: i32,
    candidate: &prost_types::EnumDescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let number_reserved = candidate.reserved_range.iter().any(|range| {
        range.start.unwrap_or_default() <= number && number <= range.end.unwrap_or_default()
    });
    let name_reserved = candidate.reserved_name.iter().any(|name| name == value);
    if !number_reserved || !name_reserved {
        violations.push(CompatibilityViolation::EnumValueRemovedWithoutReservation {
            enumeration: enumeration.to_owned(),
            value: value.to_owned(),
            number,
            number_reserved,
            name_reserved,
        });
    }
}
