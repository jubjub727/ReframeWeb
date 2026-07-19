use std::{
    fs::File,
    io::{Read as _, Write as _},
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, ensure};
use clap::Args;
use prost::Message;
use reframe_store_package::{
    PackageBuilder, PackageIdentity, PackageLimits, schema_uses_annotations,
};
use reframe_store_protocol::{
    package::Catalog,
    wire::{InterfaceVersion, ProtocolVersion},
};

#[derive(Debug, Args)]
pub(crate) struct PackArgs {
    /// Stable globally unique Store ID, such as `com.example.calendar`.
    #[arg(long)]
    store_id: String,
    /// Semantic package version recorded in the manifest.
    #[arg(long)]
    store_version: String,
    /// Public Store interface major version.
    #[arg(long)]
    interface_major: u32,
    /// Public Store interface minor version.
    #[arg(long, default_value_t = 0)]
    interface_minor: u32,
    /// Oldest fixed host protocol major version this Store accepts.
    #[arg(long, default_value_t = 1)]
    minimum_protocol_major: u32,
    /// Oldest fixed host protocol minor version this Store accepts.
    #[arg(long, default_value_t = 0)]
    minimum_protocol_minor: u32,
    /// WebAssembly Component implementing the canonical Store world.
    #[arg(long)]
    component: PathBuf,
    /// Binary protobuf `FileDescriptorSet` with source information.
    #[arg(long)]
    schema: PathBuf,
    /// Authored catalog protobuf; annotated capability bindings are regenerated.
    #[arg(long)]
    catalog: PathBuf,
    /// Permit a legacy catalog whose schema has no canonical Store annotations.
    #[arg(long)]
    legacy_catalog: bool,
    /// Destination `.rstore` archive.
    #[arg(long)]
    output: PathBuf,
    /// Replace an existing output package atomically.
    #[arg(long)]
    force: bool,
}

pub(crate) fn run(arguments: PackArgs) -> Result<()> {
    let limits = PackageLimits::default();
    let component = read_limited(
        &arguments.component,
        "component",
        limits.max_component_bytes,
    )?;
    let schema = read_limited(&arguments.schema, "schema", limits.max_schema_bytes)?;
    let catalog_bytes = read_limited(&arguments.catalog, "catalog", limits.max_catalog_bytes)?;
    let catalog =
        Catalog::decode(catalog_bytes.as_slice()).context("catalog protobuf is invalid")?;
    let identity = PackageIdentity::new(
        arguments.store_id,
        arguments.store_version,
        InterfaceVersion {
            major: arguments.interface_major,
            minor: arguments.interface_minor,
        },
        ProtocolVersion {
            major: arguments.minimum_protocol_major,
            minor: arguments.minimum_protocol_minor,
        },
    );
    enforce_annotation_policy(&schema, identity.store_id(), arguments.legacy_catalog)?;
    let archive = PackageBuilder::from_catalog(identity, component, schema, catalog).build()?;
    write_package(&arguments.output, &archive, arguments.force)?;
    println!("{}", arguments.output.display());
    Ok(())
}

fn enforce_annotation_policy(schema: &[u8], store_id: &str, allow_legacy: bool) -> Result<()> {
    let annotated = schema_uses_annotations(schema, store_id)?;
    ensure!(
        annotated || allow_legacy,
        "schema has no canonical Store annotations; pass --legacy-catalog only for an intentional legacy package"
    );
    Ok(())
}

fn write_package(path: &Path, archive: &[u8], force: bool) -> Result<()> {
    let parent = path
        .parent()
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let mut temporary = tempfile::NamedTempFile::new_in(parent).with_context(|| {
        format!(
            "could not create a temporary package in {}",
            parent.display()
        )
    })?;
    temporary.write_all(archive)?;
    temporary.as_file().sync_all()?;
    let result = if force {
        temporary.persist(path)
    } else {
        temporary.persist_noclobber(path)
    };
    result.map_err(|error| error.error).with_context(|| {
        format!(
            "could not persist Store package {}{}",
            path.display(),
            if force {
                ""
            } else {
                " (use --force to replace it)"
            }
        )
    })?;
    Ok(())
}

fn read_limited(path: &Path, name: &str, maximum_bytes: u64) -> Result<Vec<u8>> {
    let file = File::open(path)
        .with_context(|| format!("could not open {name} file {}", path.display()))?;
    let length = file
        .metadata()
        .with_context(|| format!("could not inspect {name} file {}", path.display()))?
        .len();
    ensure!(
        length <= maximum_bytes,
        "{name} file {} has {length} bytes, exceeding the {maximum_bytes}-byte limit",
        path.display()
    );

    let capacity = usize::try_from(length).unwrap_or(0);
    let mut contents = Vec::with_capacity(capacity);
    file.take(maximum_bytes.saturating_add(1))
        .read_to_end(&mut contents)
        .with_context(|| format!("could not read {name} file {}", path.display()))?;
    let actual = u64::try_from(contents.len()).unwrap_or(u64::MAX);
    ensure!(
        actual <= maximum_bytes,
        "{name} file {} grew beyond the {maximum_bytes}-byte limit while it was read",
        path.display()
    );
    Ok(contents)
}

#[cfg(test)]
mod tests {
    use std::{fs::File, io::Write as _};

    use prost::Message;
    use prost_types::FileDescriptorSet;

    use super::{enforce_annotation_policy, read_limited};

    #[test]
    fn annotation_less_packaging_requires_the_explicit_legacy_switch() {
        let legacy_schema = FileDescriptorSet::default().encode_to_vec();

        assert!(enforce_annotation_policy(&legacy_schema, "dev.reframe.legacy", false).is_err());
        enforce_annotation_policy(&legacy_schema, "dev.reframe.legacy", true)
            .expect("explicit legacy packaging");
    }

    #[test]
    fn source_files_are_bounded_before_allocation() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let path = directory.path().join("component.wasm");
        let mut file = File::create(&path).expect("source file");
        file.write_all(b"12345").expect("source bytes");
        file.sync_all().expect("source sync");

        assert!(read_limited(&path, "component", 4).is_err());
        assert_eq!(
            read_limited(&path, "component", 5).expect("bounded source"),
            b"12345"
        );
    }
}
