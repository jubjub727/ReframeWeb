use reframe_store_protocol::annotations::CAPABILITY_OPTION_FULL_NAME;

use crate::{CatalogError, VerifiedPackage, test_fixture};

use super::support::{
    annotated_archive, assert_catalog_error, entry_mut, unannotated_resource, valid_schema,
};

#[test]
fn verified_package_preserves_options_and_rejects_annotation_drift() {
    let archive = annotated_archive();
    let verified = VerifiedPackage::from_bytes(&archive).expect("verified package");
    let extension = verified
        .descriptor_pool()
        .get_extension_by_name(CAPABILITY_OPTION_FULL_NAME)
        .expect("canonical extension");
    let read = verified
        .descriptor_pool()
        .get_service_by_name("annotated_fixture.Store")
        .expect("service")
        .methods()
        .find(|method| method.name() == "Read")
        .expect("method");
    assert!(read.options().has_extension(&extension));
    assert_eq!(verified.schema_bytes(), valid_schema());

    let mut catalog = verified.catalog().clone();
    entry_mut(&mut catalog.entries, "fixture.read").title = "Drifted title".to_owned();
    assert_catalog_error(test_fixture::replace_catalog(&archive, &catalog), |error| {
        matches!(
            error,
            CatalogError::AnnotationDrift {
                entry_id,
                field: "title"
            } if entry_id == "fixture.read"
        )
    });

    let mut catalog = verified.catalog().clone();
    catalog.entries.retain(|entry| entry.id != "fixture.read");
    assert_catalog_error(
        test_fixture::replace_catalog(&archive, &catalog),
        |error| matches!(error, CatalogError::MissingAnnotatedCapability { entry_id } if entry_id == "fixture.read"),
    );

    let mut catalog = verified.catalog().clone();
    catalog.entries.push(unannotated_resource());
    assert_catalog_error(
        test_fixture::replace_catalog(&archive, &catalog),
        |error| matches!(error, CatalogError::UnannotatedCapability { entry_id } if entry_id == "fixture.legacy"),
    );
}
