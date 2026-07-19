use crate::wire::{InterfaceRequirement, InterfaceVersion, ProtocolVersion};

use super::ValidationError;

pub const CURRENT_PROTOCOL_VERSION: ProtocolVersion = ProtocolVersion { major: 1, minor: 0 };

impl ProtocolVersion {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.major == 0 {
            return Err(ValidationError::InvalidVersion {
                major: self.major,
                minor: self.minor,
                reason: "major version must be non-zero",
            });
        }
        Ok(())
    }

    pub fn ensure_supported(&self) -> Result<(), ValidationError> {
        self.validate()?;
        if self.major != CURRENT_PROTOCOL_VERSION.major
            || self.minor > CURRENT_PROTOCOL_VERSION.minor
        {
            return Err(ValidationError::UnsupportedVersion {
                found_major: self.major,
                found_minor: self.minor,
                supported_major: CURRENT_PROTOCOL_VERSION.major,
                supported_minor: CURRENT_PROTOCOL_VERSION.minor,
            });
        }
        Ok(())
    }

    #[must_use]
    pub const fn supports(&self, required: &Self) -> bool {
        self.major == required.major && self.minor >= required.minor
    }
}

impl InterfaceVersion {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.major == 0 {
            return Err(ValidationError::InvalidValue {
                field: "interface_version.major",
                reason: "major version must be non-zero",
            });
        }
        Ok(())
    }

    #[must_use]
    pub const fn satisfies(&self, requirement: &InterfaceRequirement) -> bool {
        self.major == requirement.major
            && self.minor >= requirement.min_minor
            && match requirement.max_minor {
                Some(max_minor) => self.minor <= max_minor,
                None => true,
            }
    }
}

impl InterfaceRequirement {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.major == 0 {
            return Err(ValidationError::InvalidValue {
                field: "interface_requirement.major",
                reason: "major version must be non-zero",
            });
        }
        if self.max_minor.is_some_and(|max| max < self.min_minor) {
            return Err(ValidationError::InvalidValue {
                field: "interface_requirement.max_minor",
                reason: "maximum minor must not be lower than minimum minor",
            });
        }
        Ok(())
    }
}
