use std::io::{Read, Write};
use std::path::Path;
use std::time::Duration;

use anyhow::{Context, Result};

use crate::protocol::Operation;

use super::Daemon;
use super::framing::{read_frame, write_frame};

const CLIENT_IO_TIMEOUT: Duration = Duration::from_secs(10);

pub fn serve(root: &Path) -> Result<()> {
    std::fs::create_dir_all(root).context("create workspace daemon store directory")?;
    let _lock = crate::local_socket::StoreLock::acquire(root)
        .context("acquire workspace daemon store ownership")?;
    let mut daemon = Daemon::open_with_exclusive_ownership(root)?;
    let mut input = std::io::stdin().lock();
    let mut output = std::io::stdout().lock();
    loop {
        let request = match read_frame(&mut input) {
            Ok(Some(request)) => request,
            Ok(None) => break,
            Err(error) => {
                if let Some(response) = error.client_response() {
                    write_frame(&mut output, &response)?;
                    if error.stream_is_synchronized() {
                        continue;
                    }
                    break;
                }
                return Err(error.into());
            }
        };
        let shutdown_requested = matches!(request.operation, Operation::Shutdown {});
        let response = daemon.handle(request);
        let shutdown_succeeded = shutdown_requested && response.ok;
        write_frame(&mut output, &response)?;
        if shutdown_succeeded {
            break;
        }
    }
    Ok(())
}

pub fn serve_socket(root: &Path) -> Result<()> {
    std::fs::create_dir_all(root).context("create workspace daemon store directory")?;
    let listener = crate::local_socket::LocalListener::bind(root)
        .context("bind workspace daemon local transport")?;
    let mut daemon = Daemon::open_with_exclusive_ownership(root)?;
    loop {
        let mut stream = listener.accept().context("accept daemon local client")?;
        if let Err(error) = stream.set_io_timeout(CLIENT_IO_TIMEOUT) {
            eprintln!("[workspace-daemon] could not set client I/O timeout: {error}");
            continue;
        }
        match serve_connection(&mut daemon, &mut stream) {
            Ok(true) => return Ok(()),
            Ok(false) => {}
            Err(error) => {
                eprintln!("[workspace-daemon] client request failed: {error:#}");
            }
        }
    }
}

pub(super) fn serve_connection(
    daemon: &mut Daemon,
    stream: &mut (impl Read + Write),
) -> Result<bool> {
    let request = match read_frame(stream) {
        Ok(Some(request)) => request,
        Ok(None) => return Ok(false),
        Err(error) => {
            if let Some(response) = error.client_response() {
                write_frame(stream, &response)?;
                return Ok(false);
            }
            return Err(error.into());
        }
    };
    let shutdown_requested = matches!(request.operation, Operation::Shutdown {});
    let response = daemon.handle(request);
    let shutdown_succeeded = shutdown_requested && response.ok;
    write_frame(stream, &response)?;
    Ok(shutdown_succeeded)
}
