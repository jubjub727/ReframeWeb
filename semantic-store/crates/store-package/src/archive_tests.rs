use std::io::{Cursor, Write};

use prost::Message;
use reframe_store_protocol::package::Manifest;
use sha2::{Digest, Sha256};
use zip::{CompressionMethod, ZipWriter, write::SimpleFileOptions};

use crate::{PackageError, PackageLimits, VerifiedPackage, test_fixture};

#[test]
fn valid_archive_preserves_exact_artifacts_and_hashes() {
    let archive = test_fixture::valid_archive();
    let package = VerifiedPackage::from_bytes(&archive).expect("verified package");

    assert_eq!(package.manifest().store_id, test_fixture::STORE_ID);
    assert_eq!(package.store_version().to_string(), "1.2.3");
    assert_eq!(package.component_bytes(), b"\0asm\x01\0\0\0");
    assert_eq!(package.schema_bytes(), test_fixture::schema_bytes());
    assert_eq!(package.catalog().entries.len(), 3);
    assert_eq!(
        Sha256::digest(package.catalog_bytes()).as_slice(),
        package.manifest().catalog_sha256
    );
    assert_ne!(
        package.catalog_revision().as_slice(),
        package.manifest().catalog_sha256
    );
    assert!(
        package
            .descriptor_pool()
            .get_service_by_name("fixture.Store")
            .is_some()
    );

    let cloned = package.clone();
    assert_eq!(
        cloned.catalog_bytes().as_ptr(),
        package.catalog_bytes().as_ptr()
    );
}

#[test]
fn exact_byte_tampering_is_rejected_before_catalog_decode() {
    let archive =
        test_fixture::mutate_entry(&test_fixture::valid_archive(), "catalog.pb", |bytes| {
            bytes.extend_from_slice(&[0x80])
        });

    assert!(matches!(
        VerifiedPackage::from_bytes(&archive),
        Err(PackageError::HashMismatch {
            entry: "catalog.pb",
            ..
        })
    ));
}

#[test]
fn duplicate_extra_and_traversal_names_are_rejected() {
    let base = test_fixture::valid_archive();
    let mut duplicate = base.clone();
    for offset in 0..=duplicate.len() - b"catalog.pb".len() {
        if &duplicate[offset..offset + b"catalog.pb".len()] == b"catalog.pb" {
            duplicate[offset..offset + b"catalog.pb".len()].copy_from_slice(b"store.wasm");
        }
    }
    let duplicate_error = VerifiedPackage::from_bytes(&duplicate).expect_err("duplicate name");
    assert!(
        matches!(
            duplicate_error,
            PackageError::DuplicateEntry { name: "store.wasm" }
        ),
        "unexpected error: {duplicate_error:?}"
    );

    let mut extra = test_fixture::entries(&base);
    extra.push(("notes.txt".to_owned(), Vec::new()));
    assert!(matches!(
        VerifiedPackage::from_bytes(&test_fixture::archive(&extra)),
        Err(PackageError::EntryCount { actual: 5 })
    ));

    let mut traversal = test_fixture::entries(&base);
    traversal
        .iter_mut()
        .find(|(name, _)| name == "catalog.pb")
        .expect("catalog")
        .0 = "../catalog.pb".to_owned();
    assert!(matches!(
        VerifiedPackage::from_bytes(&test_fixture::archive(&traversal)),
        Err(PackageError::UnexpectedEntry { .. })
    ));
}

#[test]
fn symlinks_are_not_package_files() {
    let entries = test_fixture::entries(&test_fixture::valid_archive());
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .unix_permissions(0o644);
    for (name, bytes) in entries.iter().filter(|(name, _)| name != "catalog.pb") {
        writer.start_file(name, options).expect("start file");
        writer.write_all(bytes).expect("write file");
    }
    writer
        .add_symlink("catalog.pb", "elsewhere", options)
        .expect("symlink");
    let archive = writer.finish().expect("finish").into_inner();

    assert!(matches!(
        VerifiedPackage::from_bytes(&archive),
        Err(PackageError::NonRegularEntry { .. })
    ));
}

#[test]
fn declared_and_observed_sizes_are_bounded() {
    let archive = test_fixture::valid_archive();
    let limits = PackageLimits {
        max_component_bytes: 7,
        ..PackageLimits::default()
    };
    assert!(matches!(
        VerifiedPackage::from_bytes_with_limits(&archive, limits),
        Err(PackageError::EntryTooLarge {
            name: "store.wasm",
            ..
        })
    ));

    let limits = PackageLimits {
        max_archive_bytes: 8,
        ..PackageLimits::default()
    };
    assert!(matches!(
        VerifiedPackage::from_bytes_with_limits(&archive, limits),
        Err(PackageError::ArchiveTooLarge { .. })
    ));
}

#[test]
fn malformed_manifest_and_digest_lengths_are_structured_errors() {
    let malformed =
        test_fixture::mutate_entry(&test_fixture::valid_archive(), "manifest.pb", |bytes| {
            *bytes = vec![0xff]
        });
    assert!(matches!(
        VerifiedPackage::from_bytes(&malformed),
        Err(PackageError::ManifestDecode(_))
    ));

    let invalid_digest =
        test_fixture::mutate_entry(&test_fixture::valid_archive(), "manifest.pb", |bytes| {
            let mut manifest = Manifest::decode(bytes.as_slice()).expect("manifest");
            manifest.schema_sha256.pop();
            *bytes = manifest.encode_to_vec();
        });
    assert!(matches!(
        VerifiedPackage::from_bytes(&invalid_digest),
        Err(PackageError::InvalidManifestField {
            field: "schema_sha256",
            ..
        })
    ));
}
