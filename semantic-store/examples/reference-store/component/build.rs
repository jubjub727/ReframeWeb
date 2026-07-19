use std::{env, fs, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let wit = reframe_store_sdk::semantic_store_wit_dir();
    let output = PathBuf::from(env::var_os("OUT_DIR").ok_or("OUT_DIR is not set")?)
        .join("semantic_store_bindings.rs");
    let path_literal = format!("{:?}", wit.to_string_lossy());
    let bindings = format!(
        r#"wit_bindgen::generate!({{
    path: {path_literal},
    world: "semantic-store",
    generate_all,
}});"#
    );
    fs::write(output, bindings)?;
    println!("cargo:rerun-if-changed={}", wit.display());
    for source in reframe_store_sdk::semantic_store_wit_files()? {
        println!("cargo:rerun-if-changed={}", source.display());
    }
    Ok(())
}
