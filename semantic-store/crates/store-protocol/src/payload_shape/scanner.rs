use prost::{
    bytes::Buf as _,
    encoding::{WireType, decode_key, decode_varint},
};
use prost_reflect::{ExtensionDescriptor, FieldDescriptor, Kind, MessageDescriptor};

use super::{
    PayloadShapeError, ProtobufShapeBudget, UnknownFieldPolicy,
    budget::{FieldLocation, ValueBudget},
    wire::{advance, is_packable, require_wire, scan_packed, skip_unknown, take_delimited},
};

pub(super) fn validate(
    descriptor: &MessageDescriptor,
    bytes: &[u8],
    limits: ProtobufShapeBudget,
    unknown_fields: UnknownFieldPolicy,
) -> Result<(), PayloadShapeError> {
    let mut budget = ValueBudget::new(limits);
    let mut input = bytes;
    scan_message(descriptor, &mut input, 0, None, unknown_fields, &mut budget)
}

fn scan_message(
    descriptor: &MessageDescriptor,
    input: &mut &[u8],
    depth: usize,
    end_group: Option<u32>,
    unknown_fields: UnknownFieldPolicy,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    if depth > budget.maximum_depth {
        return Err(PayloadShapeError::NestingLimit);
    }
    let count_base = budget.enter_message();
    let result = scan_fields(
        descriptor,
        input,
        depth,
        end_group,
        unknown_fields,
        count_base,
        budget,
    );
    budget.leave_message(count_base);
    result
}

#[allow(clippy::too_many_arguments)]
fn scan_fields(
    descriptor: &MessageDescriptor,
    input: &mut &[u8],
    depth: usize,
    end_group: Option<u32>,
    unknown_fields: UnknownFieldPolicy,
    count_base: usize,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    while input.has_remaining() {
        let (number, wire_type) = decode_key(input)?;
        if wire_type == WireType::EndGroup {
            return if end_group == Some(number) {
                Ok(())
            } else {
                Err(PayloadShapeError::UnexpectedEndGroup)
            };
        }
        budget.consume(1)?;
        let Some(field) = field(descriptor, number) else {
            match unknown_fields {
                UnknownFieldPolicy::Reject => return Err(PayloadShapeError::UnknownField),
                UnknownFieldPolicy::Skip => {
                    skip_unknown(number, wire_type, input, depth, budget)?;
                    continue;
                }
            }
        };
        scan_field(
            &field,
            number,
            wire_type,
            input,
            depth,
            unknown_fields,
            FieldLocation {
                message_name: descriptor.full_name(),
                count_base,
            },
            budget,
        )?;
    }
    if end_group.is_some() {
        Err(PayloadShapeError::UnterminatedGroup)
    } else {
        Ok(())
    }
}

#[allow(clippy::too_many_arguments)]
fn scan_field(
    field: &FieldShape,
    number: u32,
    wire_type: WireType,
    input: &mut &[u8],
    depth: usize,
    unknown_fields: UnknownFieldPolicy,
    location: FieldLocation<'_>,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    let kind = field.kind();
    if field.is_list() && wire_type == WireType::LengthDelimited && is_packable(&kind) {
        let count = scan_packed(&kind, take_delimited(input)?, budget)?;
        return budget.consume_repeated(location.message_name, number, location.count_base, count);
    }
    if field.is_list() {
        budget.consume_repeated(location.message_name, number, location.count_base, 1)?;
    }
    scan_scalar_or_message(
        field,
        number,
        wire_type,
        input,
        depth,
        unknown_fields,
        budget,
    )
}

#[allow(clippy::too_many_arguments)]
fn scan_scalar_or_message(
    field: &FieldShape,
    number: u32,
    wire_type: WireType,
    input: &mut &[u8],
    depth: usize,
    unknown_fields: UnknownFieldPolicy,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    match field.kind() {
        Kind::Message(nested) if field.is_group() => {
            require_wire(wire_type, WireType::StartGroup)?;
            budget.consume_message()?;
            scan_message(
                &nested,
                input,
                depth + 1,
                Some(number),
                unknown_fields,
                budget,
            )
        }
        Kind::Message(nested) => {
            require_wire(wire_type, WireType::LengthDelimited)?;
            budget.consume_message()?;
            let mut nested_input = take_delimited(input)?;
            scan_message(
                &nested,
                &mut nested_input,
                depth + 1,
                None,
                unknown_fields,
                budget,
            )
        }
        Kind::String | Kind::Bytes => {
            require_wire(wire_type, WireType::LengthDelimited)?;
            let _ = take_delimited(input)?;
            Ok(())
        }
        Kind::Double | Kind::Fixed64 | Kind::Sfixed64 => {
            require_wire(wire_type, WireType::SixtyFourBit)?;
            advance(input, 8)
        }
        Kind::Float | Kind::Fixed32 | Kind::Sfixed32 => {
            require_wire(wire_type, WireType::ThirtyTwoBit)?;
            advance(input, 4)
        }
        Kind::Int32
        | Kind::Int64
        | Kind::Uint32
        | Kind::Uint64
        | Kind::Sint32
        | Kind::Sint64
        | Kind::Bool
        | Kind::Enum(_) => {
            require_wire(wire_type, WireType::Varint)?;
            decode_varint(input)?;
            Ok(())
        }
    }
}

fn field(descriptor: &MessageDescriptor, number: u32) -> Option<FieldShape> {
    descriptor
        .get_field(number)
        .map(FieldShape::Field)
        .or_else(|| descriptor.get_extension(number).map(FieldShape::Extension))
}

enum FieldShape {
    Field(FieldDescriptor),
    Extension(ExtensionDescriptor),
}

impl FieldShape {
    fn kind(&self) -> Kind {
        match self {
            Self::Field(field) => field.kind(),
            Self::Extension(field) => field.kind(),
        }
    }

    fn is_group(&self) -> bool {
        match self {
            Self::Field(field) => field.is_group(),
            Self::Extension(field) => field.is_group(),
        }
    }

    fn is_list(&self) -> bool {
        match self {
            Self::Field(field) => field.is_list(),
            Self::Extension(field) => field.is_list(),
        }
    }
}
