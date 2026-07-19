use std::collections::{BTreeMap, BTreeSet};

use prost_types::{DescriptorProto, FieldDescriptorProto, field_descriptor_proto::Label};

use super::reservations;
use super::{field_shape::compare_shape, violation::CompatibilityViolation};

pub(super) fn compare_fields(
    message_name: &str,
    previous: &DescriptorProto,
    candidate: &DescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let candidate_fields = CandidateFields::new(candidate);
    let previous_numbers = previous
        .field
        .iter()
        .map(|field| field.number.unwrap_or_default())
        .collect::<BTreeSet<_>>();
    let previous_names = previous
        .field
        .iter()
        .filter_map(|field| field.name.as_deref())
        .collect::<BTreeSet<_>>();

    let mut previous_fields = previous.field.iter().collect::<Vec<_>>();
    sort_fields(&mut previous_fields);
    for previous_field in previous_fields {
        compare_field(
            message_name,
            previous,
            previous_field,
            &candidate_fields,
            violations,
        );
    }
    let mut added_fields = candidate.field.iter().collect::<Vec<_>>();
    sort_fields(&mut added_fields);
    for field in added_fields {
        let number = field.number.unwrap_or_default();
        let name = field.name.as_deref().unwrap_or_default();
        if !previous_numbers.contains(&number)
            && !previous_names.contains(name)
            && field.label == Some(Label::Required as i32)
        {
            violations.push(CompatibilityViolation::RequiredFieldAdded {
                message: message_name.to_owned(),
                field: name.to_owned(),
                number,
            });
        }
    }
    compare_reservations(message_name, previous, candidate, violations);
}

fn compare_reservations(
    message: &str,
    previous: &DescriptorProto,
    candidate: &DescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let candidate_ranges = candidate
        .reserved_range
        .iter()
        .map(|range| {
            (
                i64::from(range.start.unwrap_or_default()),
                i64::from(range.end.unwrap_or_default()),
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
            i64::from(end),
        ) {
            violations.push(CompatibilityViolation::FieldNumberReservationRemoved {
                message: message.to_owned(),
                start,
                end,
            });
        }
    }

    let candidate_names = candidate
        .reserved_name
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let previous_names = previous
        .reserved_name
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    for name in previous_names.difference(&candidate_names) {
        violations.push(CompatibilityViolation::FieldNameReservationRemoved {
            message: message.to_owned(),
            name: (*name).to_owned(),
        });
    }
}

fn compare_field(
    message_name: &str,
    previous_message: &DescriptorProto,
    previous: &FieldDescriptorProto,
    candidate_fields: &CandidateFields<'_>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let field_name = previous.name.as_deref().unwrap_or_default();
    let field_number = previous.number.unwrap_or_default();
    let same_name = candidate_fields.by_name.get(field_name).copied();
    let same_number = candidate_fields.by_number.get(&field_number).copied();
    if same_name.is_none() && same_number.is_none() {
        check_removed_field(
            message_name,
            field_name,
            field_number,
            candidate_fields.message,
            violations,
        );
        return;
    }

    compare_identity(message_name, previous, same_name, same_number, violations);
    let candidate = same_name.or(same_number).expect("field match checked");
    compare_shape(
        message_name,
        previous_message,
        candidate_fields.message,
        previous,
        candidate,
        violations,
    );
}

fn check_removed_field(
    message: &str,
    field: &str,
    number: i32,
    candidate: &DescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let number_reserved = candidate.reserved_range.iter().any(|range| {
        range.start.unwrap_or_default() <= number && number < range.end.unwrap_or_default()
    });
    let name_reserved = candidate.reserved_name.iter().any(|name| name == field);
    if !number_reserved || !name_reserved {
        violations.push(CompatibilityViolation::FieldRemovedWithoutReservation {
            message: message.to_owned(),
            field: field.to_owned(),
            number,
            number_reserved,
            name_reserved,
        });
    }
}

fn compare_identity(
    message: &str,
    previous: &FieldDescriptorProto,
    same_name: Option<&FieldDescriptorProto>,
    same_number: Option<&FieldDescriptorProto>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    let field = previous.name.as_deref().unwrap_or_default();
    let number = previous.number.unwrap_or_default();
    if let Some(candidate) = same_name
        && candidate.number != previous.number
    {
        violations.push(CompatibilityViolation::FieldNumberChanged {
            message: message.to_owned(),
            field: field.to_owned(),
            previous: number,
            candidate: candidate.number.unwrap_or_default(),
        });
    }
    if let Some(candidate) = same_number
        && candidate.name != previous.name
    {
        violations.push(CompatibilityViolation::FieldNameChanged {
            message: message.to_owned(),
            number,
            previous: field.to_owned(),
            candidate: candidate.name.clone().unwrap_or_default(),
        });
    }
}

struct CandidateFields<'a> {
    message: &'a DescriptorProto,
    by_number: BTreeMap<i32, &'a FieldDescriptorProto>,
    by_name: BTreeMap<&'a str, &'a FieldDescriptorProto>,
}

impl<'a> CandidateFields<'a> {
    fn new(message: &'a DescriptorProto) -> Self {
        Self {
            message,
            by_number: message
                .field
                .iter()
                .map(|field| (field.number.unwrap_or_default(), field))
                .collect(),
            by_name: message
                .field
                .iter()
                .filter_map(|field| Some((field.name.as_deref()?, field)))
                .collect(),
        }
    }
}

fn sort_fields(fields: &mut [&FieldDescriptorProto]) {
    fields.sort_unstable_by_key(|field| (field.number.unwrap_or_default(), field.name.as_deref()));
}
