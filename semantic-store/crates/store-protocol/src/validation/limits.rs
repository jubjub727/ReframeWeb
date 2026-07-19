use prost_types::Any;

use super::ValidationError;

pub const MAX_CAPABILITY_ID_BYTES: usize = 128;
pub const MAX_CURSOR_BYTES: usize = 512;
pub const MAX_FIELD_PATH_BYTES: usize = 512;
pub const MAX_FIELD_PATHS: usize = 128;
pub const MAX_IDEMPOTENCY_KEY_BYTES: usize = 512;
pub const MAX_INSPECTION_SECTIONS: usize = 10;
pub const MAX_QUERY_BYTES: usize = 4 * 1024;
pub const MAX_REQUESTED_CAPABILITY_KINDS: usize = 4;
pub const MAX_TYPE_NAME_BYTES: usize = 512;
pub const MAX_TYPE_URL_BYTES: usize = 512;

pub(super) fn required_text(
    field: &'static str,
    value: &str,
    maximum: usize,
) -> Result<(), ValidationError> {
    if value.trim().is_empty() {
        return Err(ValidationError::MissingField { field });
    }
    bounded_text(field, value, maximum)
}

pub(super) fn bounded_text(
    field: &'static str,
    value: &str,
    maximum: usize,
) -> Result<(), ValidationError> {
    if value.len() > maximum {
        return Err(ValidationError::InvalidValue {
            field,
            reason: "text exceeds its encoded-byte limit",
        });
    }
    Ok(())
}

pub(super) fn bounded_count(
    field: &'static str,
    actual: usize,
    maximum: usize,
) -> Result<(), ValidationError> {
    if actual > maximum {
        return Err(ValidationError::InvalidValue {
            field,
            reason: "item count exceeds its limit",
        });
    }
    Ok(())
}

pub(super) fn required_any(
    field: &'static str,
    value: Option<&Any>,
) -> Result<(), ValidationError> {
    let value = value.ok_or(ValidationError::MissingField { field })?;
    required_text(field, &value.type_url, MAX_TYPE_URL_BYTES)
}
