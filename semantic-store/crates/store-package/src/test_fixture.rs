use std::io::{Cursor, Read, Write};

use prost::Message;
use prost_types::{
    DescriptorProto, FileDescriptorProto, FileDescriptorSet, MethodDescriptorProto,
    ServiceDescriptorProto, SourceCodeInfo, source_code_info,
};
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    package::{
        Catalog, CatalogEntry, Function, Guidance, Idempotency, InterfaceVersion, Manifest,
        MethodBinding, Resource, SideEffect, Topic, catalog_entry,
    },
};
use sha2::{Digest, Sha256};
use zip::{CompressionMethod, ZipArchive, ZipWriter, write::SimpleFileOptions};

use crate::{PackageBuilder, PackageIdentity};

pub(crate) const STORE_ID: &str = "dev.reframe.fixture";

pub(crate) fn valid_archive() -> Vec<u8> {
    PackageBuilder::from_catalog(
        PackageIdentity::new(
            STORE_ID,
            "1.2.3",
            InterfaceVersion { major: 1, minor: 2 },
            CURRENT_PROTOCOL_VERSION,
        ),
        b"\0asm\x01\0\0\0".to_vec(),
        schema_bytes(),
        valid_catalog(),
    )
    .build()
    .expect("fixture package")
}

pub(crate) fn valid_catalog() -> Catalog {
    Catalog {
        display_name: "Fixture Store".to_owned(),
        overview_sentences: vec![
            "Provides deterministic fixture data.".to_owned(),
            "Exercises package verification without a runtime.".to_owned(),
        ],
        top_level_topic_ids: vec!["fixture".to_owned()],
        entries: vec![topic(), resource(), function()],
        ..Catalog::default()
    }
}

pub(crate) fn schema_bytes() -> Vec<u8> {
    let messages = ["Selector", "Value", "Input", "Output"]
        .map(|name| DescriptorProto {
            name: Some(name.to_owned()),
            ..DescriptorProto::default()
        })
        .to_vec();
    let methods = [
        ("Read", ".fixture.Selector", ".fixture.Value"),
        ("Call", ".fixture.Input", ".fixture.Output"),
    ]
    .map(|(name, input, output)| MethodDescriptorProto {
        name: Some(name.to_owned()),
        input_type: Some(input.to_owned()),
        output_type: Some(output.to_owned()),
        ..MethodDescriptorProto::default()
    })
    .to_vec();
    FileDescriptorSet {
        file: vec![FileDescriptorProto {
            name: Some("fixture.proto".to_owned()),
            package: Some("fixture".to_owned()),
            message_type: messages,
            service: vec![ServiceDescriptorProto {
                name: Some("Store".to_owned()),
                method: methods,
                ..ServiceDescriptorProto::default()
            }],
            source_code_info: Some(SourceCodeInfo {
                location: vec![source_code_info::Location {
                    span: vec![0, 0, 0],
                    ..source_code_info::Location::default()
                }],
            }),
            syntax: Some("proto3".to_owned()),
            ..FileDescriptorProto::default()
        }],
    }
    .encode_to_vec()
}

pub(crate) fn entries(archive: &[u8]) -> Vec<(String, Vec<u8>)> {
    let mut archive = ZipArchive::new(Cursor::new(archive)).expect("read fixture ZIP");
    (0..archive.len())
        .map(|index| {
            let mut entry = archive.by_index(index).expect("entry");
            let name = entry.name().to_owned();
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).expect("contents");
            (name, bytes)
        })
        .collect()
}

pub(crate) fn archive(entries: &[(String, Vec<u8>)]) -> Vec<u8> {
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .unix_permissions(0o644);
    for (name, bytes) in entries {
        writer.start_file(name, options).expect("start file");
        writer.write_all(bytes).expect("write file");
    }
    writer.finish().expect("finish ZIP").into_inner()
}

pub(crate) fn mutate_entry(base: &[u8], name: &str, mutate: impl FnOnce(&mut Vec<u8>)) -> Vec<u8> {
    let mut entries = entries(base);
    let (_, bytes) = entries
        .iter_mut()
        .find(|(entry_name, _)| entry_name == name)
        .expect("named entry");
    mutate(bytes);
    archive(&entries)
}

pub(crate) fn replace_catalog(base: &[u8], catalog: &Catalog) -> Vec<u8> {
    replace_hashed_entry(base, "catalog.pb", "catalog", catalog.encode_to_vec())
}

pub(crate) fn replace_schema(base: &[u8], schema: Vec<u8>) -> Vec<u8> {
    replace_hashed_entry(base, "schema.binpb", "schema", schema)
}

fn replace_hashed_entry(base: &[u8], file_name: &str, artifact: &str, bytes: Vec<u8>) -> Vec<u8> {
    let mut entries = entries(base);
    entries
        .iter_mut()
        .find(|(name, _)| name == file_name)
        .expect("artifact")
        .1 = bytes.clone();
    let manifest_bytes = &mut entries
        .iter_mut()
        .find(|(name, _)| name == "manifest.pb")
        .expect("manifest")
        .1;
    let mut manifest = Manifest::decode(manifest_bytes.as_slice()).expect("manifest decode");
    let hash = Sha256::digest(&bytes).to_vec();
    match artifact {
        "catalog" => manifest.catalog_sha256 = hash,
        "schema" => manifest.schema_sha256 = hash,
        _ => unreachable!(),
    }
    *manifest_bytes = manifest.encode_to_vec();
    archive(&entries)
}

fn topic() -> CatalogEntry {
    CatalogEntry {
        id: "fixture".to_owned(),
        title: "Fixture".to_owned(),
        summary: "Capabilities used to verify a Store package.".to_owned(),
        kind: Some(catalog_entry::Kind::Topic(Topic {})),
        ..CatalogEntry::default()
    }
}

fn resource() -> CatalogEntry {
    CatalogEntry {
        id: "fixture.read".to_owned(),
        parent_topic_id: "fixture".to_owned(),
        title: "Read fixture".to_owned(),
        summary: "Reads deterministic fixture data.".to_owned(),
        intent_phrases: vec!["read deterministic data".to_owned()],
        guidance: Some(guidance()),
        kind: Some(catalog_entry::Kind::Resource(Resource {
            selector_type: "fixture.Selector".to_owned(),
            value_type: "fixture.Value".to_owned(),
            supports_subscriptions: true,
            method: Some(binding("Read")),
        })),
        ..CatalogEntry::default()
    }
}

fn function() -> CatalogEntry {
    CatalogEntry {
        id: "fixture.call".to_owned(),
        parent_topic_id: "fixture".to_owned(),
        title: "Call fixture".to_owned(),
        summary: "Mutates deterministic fixture data.".to_owned(),
        related_entry_ids: vec!["fixture.read".to_owned()],
        guidance: Some(guidance()),
        kind: Some(catalog_entry::Kind::Function(Function {
            input_type: "fixture.Input".to_owned(),
            output_type: "fixture.Output".to_owned(),
            side_effect: SideEffect::WritesExternalState as i32,
            idempotency: Idempotency::IdempotentWithKey as i32,
            method: Some(binding("Call")),
        })),
        ..CatalogEntry::default()
    }
}

fn binding(method: &str) -> MethodBinding {
    MethodBinding {
        service: "fixture.Store".to_owned(),
        method: method.to_owned(),
    }
}

fn guidance() -> Guidance {
    Guidance {
        when_to_use: "Use for package conformance tests.".to_owned(),
        when_not_to_use: "Do not use for production data.".to_owned(),
        ..Guidance::default()
    }
}
