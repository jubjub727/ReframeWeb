use prost::{Message, Name};
use prost_types::Any;
use reframe_store_protocol::MAX_TYPE_URL_BYTES;

use crate::AnyError;

const TYPE_URL_PREFIX: &str = "type.googleapis.com/";

/// A generated protobuf message carrying its compile-time descriptor name.
pub trait StoreMessage: Message + Name + Default {}

impl<T> StoreMessage for T where T: Message + Name + Default {}

/// Packs a Store message into a canonical `google.protobuf.Any` value.
pub fn pack<T: StoreMessage>(message: &T) -> Result<Any, AnyError> {
    let full_name = T::full_name();
    validate_message_name(&full_name)?;
    let value = Any {
        type_url: format!("{TYPE_URL_PREFIX}{full_name}"),
        value: message.encode_to_vec(),
    };
    any_type_name(&value)?;
    Ok(value)
}

/// Decodes an `Any` after verifying its declared protobuf type exactly.
pub fn unpack<T: StoreMessage>(value: &Any) -> Result<T, AnyError> {
    let expected = T::full_name();
    validate_message_name(&expected)?;
    let actual = any_type_name(value)?;
    if actual != expected {
        return Err(AnyError::TypeMismatch {
            expected,
            actual: actual.to_owned(),
        });
    }
    T::decode(value.value.as_slice()).map_err(AnyError::Decode)
}

/// Returns the fully-qualified message name at the end of an Any type URL.
pub fn any_type_name(value: &Any) -> Result<&str, AnyError> {
    if value.type_url.len() > MAX_TYPE_URL_BYTES || value.type_url.chars().any(char::is_whitespace)
    {
        return Err(AnyError::InvalidTypeUrl);
    }
    let Some((prefix, name)) = value.type_url.rsplit_once('/') else {
        return Err(AnyError::InvalidTypeUrl);
    };
    if prefix.is_empty() || name.is_empty() {
        return Err(AnyError::InvalidTypeUrl);
    }
    validate_message_name(name)?;
    Ok(name)
}

fn validate_message_name(name: &str) -> Result<(), AnyError> {
    if name.is_empty() || name.starts_with('.') || name.ends_with('.') || name.contains('/') {
        return Err(AnyError::InvalidTypeName(name.to_owned()));
    }
    if name.split('.').any(|part| {
        part.is_empty()
            || !part
                .bytes()
                .enumerate()
                .all(|(index, byte)| is_identifier_byte(byte, index == 0))
    }) {
        return Err(AnyError::InvalidTypeName(name.to_owned()));
    }
    Ok(())
}

const fn is_identifier_byte(byte: u8, first: bool) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_' || (!first && byte.is_ascii_digit())
}
