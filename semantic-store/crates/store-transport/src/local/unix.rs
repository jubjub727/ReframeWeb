#[path = "unix/socket_file.rs"]
mod socket_file;

use std::io;
use std::os::unix::fs::PermissionsExt as _;
use std::path::Path;
use std::pin::Pin;
use std::task::{Context, Poll};

use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use tokio::net::{UnixListener, UnixStream};

use self::socket_file::{SocketGuard, prepare_endpoint};
use crate::{LocalEndpoint, local::DEFAULT_CONNECT_TIMEOUT};

#[derive(Debug)]
pub struct LocalListener {
    listener: UnixListener,
    endpoint_guard: SocketGuard,
}

impl LocalListener {
    pub fn bind(endpoint: &LocalEndpoint) -> io::Result<Self> {
        endpoint.prepare_parent()?;
        let path = endpoint.as_path();
        prepare_endpoint(path)?;
        let listener = UnixListener::bind(path)?;
        let endpoint_guard = SocketGuard::new(path)?;
        if let Err(error) = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600)) {
            drop(endpoint_guard);
            return Err(error);
        }
        Ok(Self {
            listener,
            endpoint_guard,
        })
    }

    pub async fn accept(&mut self) -> io::Result<LocalStream> {
        self.listener
            .accept()
            .await
            .map(|(stream, _address)| LocalStream(stream))
    }

    #[must_use]
    pub fn endpoint(&self) -> &Path {
        &self.endpoint_guard.path
    }
}

#[derive(Debug)]
pub struct LocalStream(UnixStream);

impl AsyncRead for LocalStream {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().0).poll_read(context, buffer)
    }
}

impl AsyncWrite for LocalStream {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<Result<usize, io::Error>> {
        Pin::new(&mut self.get_mut().0).poll_write(context, buffer)
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Result<(), io::Error>> {
        Pin::new(&mut self.get_mut().0).poll_flush(context)
    }

    fn poll_shutdown(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), io::Error>> {
        Pin::new(&mut self.get_mut().0).poll_shutdown(context)
    }
}

pub async fn connect(endpoint: &LocalEndpoint) -> io::Result<LocalStream> {
    connect_with_timeout(endpoint, DEFAULT_CONNECT_TIMEOUT).await
}

pub async fn connect_with_timeout(
    endpoint: &LocalEndpoint,
    timeout: std::time::Duration,
) -> io::Result<LocalStream> {
    endpoint.prepare_parent()?;
    let deadline = tokio::time::Instant::now()
        .checked_add(timeout)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "timeout is out of range"))?;
    tokio::time::timeout_at(deadline, UnixStream::connect(endpoint.as_path()))
        .await
        .map_err(|_elapsed| io::Error::new(io::ErrorKind::TimedOut, "local connection timed out"))?
        .map(LocalStream)
}
