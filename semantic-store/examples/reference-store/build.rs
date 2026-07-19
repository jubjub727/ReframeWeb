use std::{env, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto = PathBuf::from("proto/reference_store.proto");
    let descriptor = PathBuf::from(env::var_os("OUT_DIR").ok_or("OUT_DIR is not set")?)
        .join("reference_store_descriptor.bin");
    let annotation_include = reframe_store_sdk::annotation_proto_include_dir();
    let protoc_include = protoc_bin_vendored::include_path()?;

    let mut config = prost_build::Config::new();
    config
        .enable_type_names()
        .protoc_executable(protoc_bin_vendored::protoc_bin_path()?)
        .file_descriptor_set_path(descriptor)
        .compile_protos(
            &[proto],
            &[
                PathBuf::from("proto"),
                annotation_include.to_path_buf(),
                protoc_include,
            ],
        )?;

    println!("cargo:rerun-if-changed=proto/reference_store.proto");
    Ok(())
}
