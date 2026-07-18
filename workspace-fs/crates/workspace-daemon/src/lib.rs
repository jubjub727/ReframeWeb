mod daemon;
mod local_socket;
mod model;
mod paths;
mod protocol;
mod resident;
mod session;
mod store;

#[cfg(unix)]
mod unix_vfs;
#[cfg(windows)]
mod windows_vfs;

use std::path::PathBuf;

use anyhow::{Result, bail};

pub fn run() -> Result<()> {
    let (store, command) = arguments()?;
    match command.as_str() {
        "serve" => daemon::serve(&store),
        "serve-socket" => daemon::serve_socket(&store),
        _ => bail!("the workspace backing service supports 'serve' and 'serve-socket'"),
    }
}

fn arguments() -> Result<(PathBuf, String)> {
    let mut arguments = std::env::args().skip(1);
    let mut store = std::env::var_os("REFRAME_WORKSPACE_STORE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(".reframe-workspace"));
    let mut command = None;
    while let Some(argument) = arguments.next() {
        if argument == "--store" {
            store = PathBuf::from(
                arguments
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--store requires a path"))?,
            );
        } else if command.replace(argument).is_some() {
            bail!("unexpected backing-service argument");
        }
    }
    Ok((
        store,
        command.ok_or_else(|| anyhow::anyhow!("missing backing-service command"))?,
    ))
}
