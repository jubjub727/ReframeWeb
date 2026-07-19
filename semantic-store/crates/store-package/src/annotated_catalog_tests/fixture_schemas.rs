use std::{collections::HashMap, fs, process::Command, sync::OnceLock};

const FIXTURES: &[&str] = &[
    "annotated_valid",
    "annotated_duplicate",
    "annotated_missing_kind",
    "annotated_invalid_store_service",
    "annotated_empty_store",
    "annotated_unannotated_method",
    "annotated_unspecified_function",
    "annotated_streaming",
];

pub(super) fn schema(name: &str) -> &'static [u8] {
    static SCHEMAS: OnceLock<HashMap<&'static str, Vec<u8>>> = OnceLock::new();
    SCHEMAS
        .get_or_init(compile_all)
        .get(name)
        .unwrap_or_else(|| panic!("unknown fixture {name}"))
}

fn compile_all() -> HashMap<&'static str, Vec<u8>> {
    let fixture_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/proto");
    let output_dir = tempfile::tempdir().expect("fixture output directory");
    let protoc = protoc_bin_vendored::protoc_bin_path().expect("vendored protoc");
    let well_known = protoc_bin_vendored::include_path().expect("vendored protobuf includes");
    let annotations = reframe_store_protocol::annotation_proto_include_dir();

    FIXTURES
        .iter()
        .map(|&fixture| {
            let input = fixture_dir.join(format!("{fixture}.proto"));
            let output = output_dir.path().join(format!("{fixture}.binpb"));
            let status = Command::new(&protoc)
                .arg("--include_imports")
                .arg("--include_source_info")
                .arg(format!("--descriptor_set_out={}", output.display()))
                .arg(format!("--proto_path={}", fixture_dir.display()))
                .arg(format!("--proto_path={}", annotations.display()))
                .arg(format!("--proto_path={}", well_known.display()))
                .arg(&input)
                .status()
                .expect("run vendored protoc");
            assert!(status.success(), "protoc failed for {}", input.display());
            (
                fixture,
                fs::read(output).expect("compiled descriptor fixture"),
            )
        })
        .collect()
}
