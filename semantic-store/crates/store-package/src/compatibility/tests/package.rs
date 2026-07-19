use prost::Message;
use prost_types::{DescriptorProto, FileDescriptorSet};
use reframe_store_protocol::package::catalog_entry;

use super::super::{CompatibilityError, CompatibilityViolation, check_package_compatibility};
use crate::{VerifiedPackage, test_fixture};

#[test]
fn identical_verified_packages_are_compatible() {
    let package = verified(&test_fixture::valid_archive());

    assert_eq!(check_package_compatibility(&package, &package), Ok(()));
}

#[test]
fn public_api_reports_catalog_contract_breaks() {
    let base = test_fixture::valid_archive();
    let previous = verified(&base);
    let mut catalog = previous.catalog().clone();
    let resource = catalog
        .entries
        .iter_mut()
        .find_map(|entry| match entry.kind.as_mut()? {
            catalog_entry::Kind::Resource(resource) => Some(resource),
            _ => None,
        })
        .expect("fixture resource");
    resource.supports_subscriptions = false;
    let candidate = verified(&test_fixture::replace_catalog(&base, &catalog));

    let CompatibilityError::BreakingChanges(issues) =
        check_package_compatibility(&previous, &candidate).expect_err("breaking catalog")
    else {
        panic!("expected structured compatibility issues");
    };
    assert_eq!(
        issues.violations(),
        [CompatibilityViolation::ResourceSubscriptionsDisabled {
            capability_id: "fixture.read".to_owned(),
        }]
    );
}

#[test]
fn public_api_reports_descriptor_breaks() {
    let candidate_archive = test_fixture::valid_archive();
    let mut previous_schema =
        FileDescriptorSet::decode(test_fixture::schema_bytes().as_slice()).expect("fixture schema");
    previous_schema.file[0].message_type.push(DescriptorProto {
        name: Some("Retired".to_owned()),
        ..DescriptorProto::default()
    });
    let previous_archive =
        test_fixture::replace_schema(&candidate_archive, previous_schema.encode_to_vec());
    let previous = verified(&previous_archive);
    let candidate = verified(&candidate_archive);

    let CompatibilityError::BreakingChanges(issues) =
        check_package_compatibility(&previous, &candidate).expect_err("removed message")
    else {
        panic!("expected structured compatibility issues");
    };
    assert_eq!(
        issues.violations(),
        [CompatibilityViolation::MessageRemoved {
            message: "fixture.Retired".to_owned(),
        }]
    );
    assert!(issues.to_string().contains("candidate Store interface"));
}

fn verified(bytes: &[u8]) -> VerifiedPackage {
    VerifiedPackage::from_bytes(bytes).expect("verified package")
}
