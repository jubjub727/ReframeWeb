mod pack;

use std::{
    fs::File,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
use reframe_store_host::StoreHost;
use reframe_store_package::{PackageLimits, VerifiedPackage, check_package_compatibility};
use reframe_store_runtime::{EngineConfig, RuntimeConfig};
use reframe_store_transport::LocalEndpoint;
use tokio_util::sync::CancellationToken;
use tracing_subscriber::EnvFilter;

#[derive(Debug, Parser)]
#[command(
    name = "reframe-store-host",
    version,
    about = "Local Semantic Store conformance host"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Verify package structure, hashes, descriptors, and catalog bindings.
    Verify {
        /// One or more `.rstore` packages to verify, including their component ABI.
        #[arg(required = true, value_name = "PACKAGE")]
        packages: Vec<PathBuf>,
    },
    /// Build a strict .rstore from component, schema, and catalog artifacts.
    Pack(pack::PackArgs),
    /// Check that a candidate package is backward compatible with a previous package.
    CheckCompat {
        /// Previously released package whose public contract must remain supported.
        #[arg(long)]
        previous: PathBuf,
        /// Candidate package to compare against the previous release.
        #[arg(long)]
        candidate: PathBuf,
    },
    /// Serve one or more verified Store packages over the platform-local endpoint.
    Serve {
        /// Verified `.rstore` package to install; repeat for multiple Store IDs.
        #[arg(long = "package", required = true)]
        packages: Vec<PathBuf>,
        /// Stable logical name used to derive the protected local endpoint.
        #[arg(long, default_value = "reframe-semantic-store")]
        service_name: String,
        /// Maximum number of simultaneously open sessions across all clients.
        #[arg(long, default_value_t = 1_024)]
        max_sessions: usize,
        /// Maximum active invocations retained by any one session.
        #[arg(long, default_value_t = 128)]
        max_invocations_per_session: usize,
    },
}

pub(crate) async fn run() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Verify { packages } => verify(packages).await,
        Command::Pack(arguments) => pack::run(arguments),
        Command::CheckCompat {
            previous,
            candidate,
        } => check_compat(&previous, &candidate),
        Command::Serve {
            packages,
            service_name,
            max_sessions,
            max_invocations_per_session,
        } => {
            init_tracing();
            serve(
                packages,
                &service_name,
                max_sessions,
                max_invocations_per_session,
            )
            .await
        }
    }
}

fn check_compat(previous_path: &Path, candidate_path: &Path) -> Result<()> {
    let previous = load_package(previous_path)?;
    let candidate = load_package(candidate_path)?;
    check_package_compatibility(&previous, &candidate)
        .context("candidate Store package is not backward compatible")?;
    let previous_interface = previous.interface_version();
    let candidate_interface = candidate.interface_version();
    println!(
        "compatible\t{}\tinterface={}.{} -> {}.{}",
        candidate.manifest().store_id,
        previous_interface.major,
        previous_interface.minor,
        candidate_interface.major,
        candidate_interface.minor,
    );
    Ok(())
}

async fn verify(paths: Vec<PathBuf>) -> Result<()> {
    ensure!(!paths.is_empty(), "at least one package path is required");
    let packages = paths
        .iter()
        .map(|path| load_package(path.as_path()))
        .collect::<Result<Vec<_>>>()?;
    StoreHost::new(
        packages.iter().cloned(),
        EngineConfig::default(),
        RuntimeConfig::default(),
    )
    .await
    .context("Store component ABI verification failed")?;
    for package in packages {
        let interface = package.interface_version();
        println!(
            "{}\t{}\tinterface={}.{}\tcatalog={}",
            package.manifest().store_id,
            package.store_version(),
            interface.major,
            interface.minor,
            hex::encode(package.catalog_revision()),
        );
    }
    Ok(())
}

async fn serve(
    paths: Vec<PathBuf>,
    service_name: &str,
    max_sessions: usize,
    max_invocations: usize,
) -> Result<()> {
    let packages = paths
        .iter()
        .map(|path| load_package(path.as_path()))
        .collect::<Result<Vec<_>>>()?;
    let runtime_config = RuntimeConfig::default()
        .with_max_sessions(max_sessions)?
        .with_max_invocations_per_session(max_invocations)?;
    let host = StoreHost::new(packages, EngineConfig::default(), runtime_config).await?;
    let endpoint = LocalEndpoint::for_service(service_name)?;
    let shutdown = CancellationToken::new();
    let signal = shutdown.clone();
    tokio::spawn(async move {
        if let Err(error) = tokio::signal::ctrl_c().await {
            tracing::error!(%error, "failed to listen for Ctrl+C");
        }
        signal.cancel();
    });
    host.serve(&endpoint, shutdown).await?;
    Ok(())
}

fn load_package(path: &Path) -> Result<VerifiedPackage> {
    let file = File::open(path)
        .with_context(|| format!("could not open Store package {}", path.display()))?;
    VerifiedPackage::read(file, PackageLimits::default())
        .with_context(|| format!("Store package {} is invalid", path.display()))
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_writer(std::io::stderr)
        .init();
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use clap::Parser;

    use super::{Cli, Command};

    #[test]
    fn check_compat_accepts_explicit_previous_and_candidate_paths() {
        let cli = Cli::try_parse_from([
            "reframe-store-host",
            "check-compat",
            "--previous",
            "old.rstore",
            "--candidate",
            "new.rstore",
        ])
        .expect("valid command");

        assert!(matches!(
            cli.command,
            Command::CheckCompat {
                previous,
                candidate
            } if previous.as_path() == Path::new("old.rstore")
                && candidate.as_path() == Path::new("new.rstore")
        ));
    }

    #[test]
    fn verify_requires_at_least_one_package_path() {
        assert!(Cli::try_parse_from(["reframe-store-host", "verify"]).is_err());
    }
}
