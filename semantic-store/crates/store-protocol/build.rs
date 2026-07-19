use std::{env, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest_dir =
        PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").ok_or("CARGO_MANIFEST_DIR")?);
    let proto_dir = manifest_dir.join("../../proto");
    let annotation_proto_dir = manifest_dir.join("proto");
    let annotations =
        annotation_proto_dir.join("reframe/semantic_store/options/v1/annotations.proto");
    let out_dir = PathBuf::from(env::var_os("OUT_DIR").ok_or("OUT_DIR")?);
    let protoc = protoc_bin_vendored::protoc_bin_path()?;
    let protoc_include = protoc_bin_vendored::include_path()?;

    println!("cargo:rerun-if-changed={}", proto_dir.display());
    println!("cargo:rerun-if-changed={}", annotations.display());

    let mut config = prost_build::Config::new();
    config.protoc_executable(protoc);
    config.enum_attribute(
        ".reframe.semantic_store.v1.Envelope.message",
        "#[allow(clippy::large_enum_variant)]",
    );
    config.file_descriptor_set_path(out_dir.join("semantic_store_descriptor.bin"));
    config.compile_protos(
        &[
            proto_dir.join("types.proto"),
            proto_dir.join("package.proto"),
            proto_dir.join("wire.proto"),
            annotations,
        ],
        &[proto_dir, annotation_proto_dir, protoc_include],
    )?;
    Ok(())
}
