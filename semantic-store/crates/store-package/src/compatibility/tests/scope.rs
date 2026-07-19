use reframe_store_protocol::package::{InterfaceVersion, ProtocolVersion};

use super::super::{CompatibilityError, check_scope};

#[test]
fn scope_requires_the_same_store_and_interface_major_without_minor_regression() {
    let previous_interface = interface(2, 4);
    let previous_protocol = protocol(1, 3);

    assert_eq!(
        check_scope(
            "dev.reframe.one",
            &previous_interface,
            &previous_protocol,
            "dev.reframe.two",
            &previous_interface,
            &previous_protocol,
        ),
        Err(CompatibilityError::StoreIdMismatch {
            previous: "dev.reframe.one".to_owned(),
            candidate: "dev.reframe.two".to_owned(),
        })
    );
    assert_eq!(
        check_scope(
            "dev.reframe.one",
            &previous_interface,
            &previous_protocol,
            "dev.reframe.one",
            &interface(3, 0),
            &previous_protocol,
        ),
        Err(CompatibilityError::InterfaceMajorMismatch {
            previous: 2,
            candidate: 3,
        })
    );
    assert_eq!(
        check_scope(
            "dev.reframe.one",
            &previous_interface,
            &previous_protocol,
            "dev.reframe.one",
            &interface(2, 3),
            &previous_protocol,
        ),
        Err(CompatibilityError::InterfaceMinorRegression {
            previous: 4,
            candidate: 3,
        })
    );
}

#[test]
fn raised_minimum_protocol_requirement_is_breaking() {
    let store_interface = interface(1, 7);

    assert_eq!(
        check_scope(
            "dev.reframe.store",
            &store_interface,
            &protocol(1, 2),
            "dev.reframe.store",
            &store_interface,
            &protocol(2, 0),
        ),
        Err(CompatibilityError::MinimumProtocolMajorChanged {
            previous: 1,
            candidate: 2,
        })
    );
    assert_eq!(
        check_scope(
            "dev.reframe.store",
            &store_interface,
            &protocol(1, 2),
            "dev.reframe.store",
            &store_interface,
            &protocol(1, 3),
        ),
        Err(CompatibilityError::MinimumProtocolMinorIncreased {
            previous: 2,
            candidate: 3,
        })
    );
    assert_eq!(
        check_scope(
            "dev.reframe.store",
            &store_interface,
            &protocol(1, 2),
            "dev.reframe.store",
            &interface(1, 8),
            &protocol(1, 1),
        ),
        Ok(())
    );
}

const fn interface(major: u32, minor: u32) -> InterfaceVersion {
    InterfaceVersion { major, minor }
}

const fn protocol(major: u32, minor: u32) -> ProtocolVersion {
    ProtocolVersion { major, minor }
}
