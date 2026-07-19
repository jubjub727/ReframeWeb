#[test]
fn canonical_wit_tree_is_owned_by_the_sdk_package() {
    let root = reframe_store_sdk::semantic_store_wit_dir();

    assert!(root.join("semantic-store.wit").is_file());
    assert!(root.join("deps/http.wit").is_file());
    assert!(root.join("deps/io.wit").is_file());

    let files = reframe_store_sdk::semantic_store_wit_files().unwrap();
    assert!(files.windows(2).all(|pair| pair[0] < pair[1]));
    assert!(files.contains(&root.join("semantic-store.wit")));
    assert!(files.contains(&root.join("deps/http.wit")));
}

#[test]
fn cargo_package_explicitly_includes_the_wit_tree() {
    let manifest = include_str!("../Cargo.toml");
    assert!(manifest.contains("\"/wit/**\""));
}
