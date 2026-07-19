use std::{env, fs, path::PathBuf};

use reframe_reference_store::{build_package, componentize};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (component_path, output_path) = paths()?;
    let module = fs::read(&component_path)?;
    let package = build_package(componentize(&module)?)?;
    fs::write(&output_path, package)?;
    println!("wrote {}", output_path.display());
    Ok(())
}

fn paths() -> Result<(PathBuf, PathBuf), Box<dyn std::error::Error>> {
    let mut args = env::args_os().skip(1);
    let component = args
        .next()
        .ok_or("usage: package-reference-store <store-component.wasm> <output.rstore>")?;
    let output = args
        .next()
        .ok_or("usage: package-reference-store <store-component.wasm> <output.rstore>")?;
    if args.next().is_some() {
        return Err("package-reference-store accepts exactly two paths".into());
    }
    Ok((component.into(), output.into()))
}
