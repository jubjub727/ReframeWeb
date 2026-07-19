use prost::{
    bytes::Buf as _,
    encoding::{WireType, decode_key, decode_varint},
};
use prost_reflect::Kind;

use super::{PayloadShapeError, budget::ValueBudget};

pub(super) fn skip_unknown(
    number: u32,
    wire_type: WireType,
    input: &mut &[u8],
    depth: usize,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    match wire_type {
        WireType::Varint => {
            decode_varint(input)?;
            Ok(())
        }
        WireType::SixtyFourBit => advance(input, 8),
        WireType::LengthDelimited => {
            let _ = take_delimited(input)?;
            Ok(())
        }
        WireType::StartGroup => skip_unknown_group(number, input, depth + 1, budget),
        WireType::EndGroup => Err(PayloadShapeError::UnexpectedEndGroup),
        WireType::ThirtyTwoBit => advance(input, 4),
    }
}

fn skip_unknown_group(
    group_number: u32,
    input: &mut &[u8],
    depth: usize,
    budget: &mut ValueBudget,
) -> Result<(), PayloadShapeError> {
    if depth > budget.maximum_depth {
        return Err(PayloadShapeError::NestingLimit);
    }
    while input.has_remaining() {
        let (number, wire_type) = decode_key(input)?;
        if wire_type == WireType::EndGroup {
            return if number == group_number {
                Ok(())
            } else {
                Err(PayloadShapeError::UnexpectedEndGroup)
            };
        }
        budget.consume(1)?;
        skip_unknown(number, wire_type, input, depth, budget)?;
    }
    Err(PayloadShapeError::UnterminatedGroup)
}

pub(super) fn scan_packed(
    kind: &Kind,
    mut input: &[u8],
    budget: &mut ValueBudget,
) -> Result<usize, PayloadShapeError> {
    match kind {
        Kind::Double | Kind::Fixed64 | Kind::Sfixed64 => scan_fixed(input, 8, budget),
        Kind::Float | Kind::Fixed32 | Kind::Sfixed32 => scan_fixed(input, 4, budget),
        Kind::Int32
        | Kind::Int64
        | Kind::Uint32
        | Kind::Uint64
        | Kind::Sint32
        | Kind::Sint64
        | Kind::Bool
        | Kind::Enum(_) => {
            let mut count = 0_usize;
            while input.has_remaining() {
                budget.consume(1)?;
                decode_varint(&mut input)?;
                count = count.checked_add(1).ok_or(PayloadShapeError::ValueLimit)?;
            }
            Ok(count)
        }
        _ => Err(PayloadShapeError::MalformedPackedField),
    }
}

fn scan_fixed(
    input: &[u8],
    width: usize,
    budget: &mut ValueBudget,
) -> Result<usize, PayloadShapeError> {
    if !input.len().is_multiple_of(width) {
        return Err(PayloadShapeError::MalformedPackedField);
    }
    let count = input.len() / width;
    budget.consume(count)?;
    Ok(count)
}

pub(super) const fn is_packable(kind: &Kind) -> bool {
    !matches!(kind, Kind::String | Kind::Bytes | Kind::Message(_))
}

pub(super) fn take_delimited<'a>(input: &mut &'a [u8]) -> Result<&'a [u8], PayloadShapeError> {
    let length = decode_varint(input)?;
    let length = usize::try_from(length).map_err(|_| PayloadShapeError::TruncatedField)?;
    if length > input.len() {
        return Err(PayloadShapeError::TruncatedField);
    }
    let (value, remaining) = input.split_at(length);
    *input = remaining;
    Ok(value)
}

pub(super) fn advance(input: &mut &[u8], length: usize) -> Result<(), PayloadShapeError> {
    if length > input.len() {
        return Err(PayloadShapeError::TruncatedField);
    }
    input.advance(length);
    Ok(())
}

pub(super) fn require_wire(actual: WireType, expected: WireType) -> Result<(), PayloadShapeError> {
    if actual == expected {
        Ok(())
    } else {
        Err(PayloadShapeError::WrongWireType)
    }
}
