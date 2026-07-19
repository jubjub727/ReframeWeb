mod envelope;
mod invocation;
mod limits;
mod version;

use thiserror::Error;
use uuid::Uuid;

pub use limits::{
    MAX_CAPABILITY_ID_BYTES, MAX_CURSOR_BYTES, MAX_FIELD_PATH_BYTES, MAX_FIELD_PATHS,
    MAX_IDEMPOTENCY_KEY_BYTES, MAX_INSPECTION_SECTIONS, MAX_QUERY_BYTES,
    MAX_REQUESTED_CAPABILITY_KINDS, MAX_TYPE_NAME_BYTES, MAX_TYPE_URL_BYTES,
};
pub use version::CURRENT_PROTOCOL_VERSION;

#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum ValidationError {
    #[error("required field `{field}` is missing")]
    MissingField { field: &'static str },
    #[error("`{field}` is not a UUID")]
    InvalidUuid { field: &'static str },
    #[error("invalid protocol version {major}.{minor}: {reason}")]
    InvalidVersion {
        major: u32,
        minor: u32,
        reason: &'static str,
    },
    #[error(
        "protocol version {found_major}.{found_minor} is unsupported; host supports {supported_major}.{supported_minor}"
    )]
    UnsupportedVersion {
        found_major: u32,
        found_minor: u32,
        supported_major: u32,
        supported_minor: u32,
    },
    #[error("invalid `{field}`: {reason}")]
    InvalidValue {
        field: &'static str,
        reason: &'static str,
    },
    #[error("fields `{left}` and `{right}` do not agree")]
    MismatchedFields {
        left: &'static str,
        right: &'static str,
    },
}

pub fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, ValidationError> {
    // UUID parsers accept several textual forms. Refuse unbounded inputs before
    // parsing, and never retain attacker-controlled text in the resulting fault.
    if value.len() > 45 {
        return Err(ValidationError::InvalidUuid { field });
    }
    Uuid::parse_str(value).map_err(|_| ValidationError::InvalidUuid { field })
}

pub fn validate_uuid(field: &'static str, value: &str) -> Result<(), ValidationError> {
    parse_uuid(field, value).map(|_| ())
}

pub fn validate_store_id(value: &str) -> Result<(), ValidationError> {
    let structurally_valid = !value.is_empty()
        && value.len() <= 253
        && value.split('.').all(|segment| {
            segment.len() <= 63
                && segment
                    .as_bytes()
                    .first()
                    .is_some_and(u8::is_ascii_alphanumeric)
                && segment.as_bytes().iter().all(|byte| {
                    byte.is_ascii_lowercase()
                        || byte.is_ascii_digit()
                        || matches!(byte, b'_' | b'-')
                })
        });
    if !structurally_valid || Uuid::parse_str(value).is_ok() {
        return Err(ValidationError::InvalidValue {
            field: "store_id",
            reason: "must be a bounded lowercase DNS-like identifier",
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use crate::wire::ProtocolVersion;

    use super::*;

    #[test]
    fn versions_are_directional() {
        let offered = ProtocolVersion { major: 1, minor: 3 };
        assert!(offered.supports(&ProtocolVersion { major: 1, minor: 2 }));
        assert!(!offered.supports(&ProtocolVersion { major: 2, minor: 0 }));
    }

    #[test]
    fn store_ids_are_stable_textual_ids() {
        assert!(validate_store_id("dev.reframe.weather-store").is_ok());
        assert!(validate_store_id("550e8400-e29b-41d4-a716-446655440000").is_err());
        assert!(validate_store_id("Reframe.Weather").is_err());
        assert!(validate_store_id("reframe..weather").is_err());
    }

    #[test]
    fn invalid_uuid_errors_never_echo_attacker_controlled_text() {
        let error = parse_uuid("request_id", &"x".repeat(1024 * 1024)).unwrap_err();
        assert_eq!(
            error,
            ValidationError::InvalidUuid {
                field: "request_id"
            }
        );
        assert!(error.to_string().len() < 64);
    }
}
