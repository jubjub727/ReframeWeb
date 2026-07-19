//! Backward-compatibility checks for successive Store interface revisions.

mod catalog;
mod enums;
mod error;
mod field_shape;
mod fields;
mod index;
mod messages;
mod reservations;
mod services;
mod violation;

#[cfg(test)]
mod test_schema;
#[cfg(test)]
mod tests;

use reframe_store_protocol::package::{InterfaceVersion, ProtocolVersion};

use crate::VerifiedPackage;

use catalog::compare_catalog;
use enums::compare_enums;
pub use error::{CompatibilityError, CompatibilityIssues};
use index::SchemaIndex;
use messages::compare_messages;
use services::compare_services;
pub use violation::CompatibilityViolation;

/// Checks that `candidate` is an additive, backward-compatible revision of
/// `previous` for the same Store and semantic-interface major version.
///
/// Store identity/version scope failures are reported separately from catalog
/// and descriptor changes. The candidate cannot regress its interface minor,
/// change its minimum protocol major, or raise its minimum protocol minor.
/// Additive messages, enums, services, methods, optional fields, and enum values
/// pass.
pub fn check_package_compatibility(
    previous: &VerifiedPackage,
    candidate: &VerifiedPackage,
) -> Result<(), CompatibilityError> {
    check_scope(
        &previous.manifest().store_id,
        previous.interface_version(),
        previous
            .manifest()
            .minimum_protocol_version
            .as_ref()
            .expect("verified package has a minimum protocol version"),
        &candidate.manifest().store_id,
        candidate.interface_version(),
        candidate
            .manifest()
            .minimum_protocol_version
            .as_ref()
            .expect("verified package has a minimum protocol version"),
    )?;
    let mut violations = Vec::new();
    compare_catalog(previous.catalog(), candidate.catalog(), &mut violations);
    violations.extend(
        compare_descriptor_sets(previous.descriptor_set(), candidate.descriptor_set())
            .into_violations(),
    );
    let issues = CompatibilityIssues::new(violations);
    if issues.is_empty() {
        Ok(())
    } else {
        Err(issues.into())
    }
}

fn check_scope(
    previous_store_id: &str,
    previous_interface: &InterfaceVersion,
    previous_protocol: &ProtocolVersion,
    candidate_store_id: &str,
    candidate_interface: &InterfaceVersion,
    candidate_protocol: &ProtocolVersion,
) -> Result<(), CompatibilityError> {
    if previous_store_id != candidate_store_id {
        return Err(CompatibilityError::StoreIdMismatch {
            previous: previous_store_id.to_owned(),
            candidate: candidate_store_id.to_owned(),
        });
    }
    if previous_interface.major != candidate_interface.major {
        return Err(CompatibilityError::InterfaceMajorMismatch {
            previous: previous_interface.major,
            candidate: candidate_interface.major,
        });
    }
    if candidate_interface.minor < previous_interface.minor {
        return Err(CompatibilityError::InterfaceMinorRegression {
            previous: previous_interface.minor,
            candidate: candidate_interface.minor,
        });
    }
    if previous_protocol.major != candidate_protocol.major {
        return Err(CompatibilityError::MinimumProtocolMajorChanged {
            previous: previous_protocol.major,
            candidate: candidate_protocol.major,
        });
    }
    if candidate_protocol.minor > previous_protocol.minor {
        return Err(CompatibilityError::MinimumProtocolMinorIncreased {
            previous: previous_protocol.minor,
            candidate: candidate_protocol.minor,
        });
    }
    Ok(())
}

fn compare_descriptor_sets(
    previous: &prost_types::FileDescriptorSet,
    candidate: &prost_types::FileDescriptorSet,
) -> CompatibilityIssues {
    let previous = SchemaIndex::new(previous);
    let candidate = SchemaIndex::new(candidate);
    let mut violations = Vec::new();
    compare_messages(&previous, &candidate, &mut violations);
    compare_enums(&previous, &candidate, &mut violations);
    compare_services(&previous, &candidate, &mut violations);
    CompatibilityIssues::new(violations)
}
