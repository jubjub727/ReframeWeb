use std::io;
use std::pin::Pin;
use std::task::{Context, Poll};

use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use tokio::net::windows::named_pipe::{
    ClientOptions, NamedPipeClient, NamedPipeServer, ServerOptions,
};

use super::windows_security;
use crate::{LocalEndpoint, local::DEFAULT_CONNECT_TIMEOUT};

#[derive(Debug)]
pub struct LocalListener {
    pipe_name: String,
    pending: Option<NamedPipeServer>,
}

impl LocalListener {
    pub fn bind(endpoint: &LocalEndpoint) -> io::Result<Self> {
        let pipe_name = endpoint.as_pipe_name().to_owned();
        let pending = create_server(&pipe_name, true)?;
        Ok(Self {
            pipe_name,
            pending: Some(pending),
        })
    }

    pub async fn accept(&mut self) -> io::Result<LocalStream> {
        let server = match self.pending.take() {
            Some(server) => server,
            None => create_server(&self.pipe_name, false)?,
        };
        server.connect().await?;
        self.pending = Some(create_server(&self.pipe_name, false)?);
        Ok(LocalStream(PipeStream::Server(server)))
    }

    #[must_use]
    pub fn endpoint(&self) -> &str {
        &self.pipe_name
    }
}

#[derive(Debug)]
pub struct LocalStream(PipeStream);

#[derive(Debug)]
enum PipeStream {
    Client(NamedPipeClient),
    Server(NamedPipeServer),
}

impl AsyncRead for LocalStream {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        match &mut self.get_mut().0 {
            PipeStream::Client(stream) => Pin::new(stream).poll_read(context, buffer),
            PipeStream::Server(stream) => Pin::new(stream).poll_read(context, buffer),
        }
    }
}

impl AsyncWrite for LocalStream {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<Result<usize, io::Error>> {
        match &mut self.get_mut().0 {
            PipeStream::Client(stream) => Pin::new(stream).poll_write(context, buffer),
            PipeStream::Server(stream) => Pin::new(stream).poll_write(context, buffer),
        }
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Result<(), io::Error>> {
        match &mut self.get_mut().0 {
            PipeStream::Client(stream) => Pin::new(stream).poll_flush(context),
            PipeStream::Server(stream) => Pin::new(stream).poll_flush(context),
        }
    }

    fn poll_shutdown(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), io::Error>> {
        match &mut self.get_mut().0 {
            PipeStream::Client(stream) => Pin::new(stream).poll_shutdown(context),
            PipeStream::Server(stream) => Pin::new(stream).poll_shutdown(context),
        }
    }
}

pub async fn connect(endpoint: &LocalEndpoint) -> io::Result<LocalStream> {
    connect_with_timeout(endpoint, DEFAULT_CONNECT_TIMEOUT).await
}

pub async fn connect_with_timeout(
    endpoint: &LocalEndpoint,
    timeout: std::time::Duration,
) -> io::Result<LocalStream> {
    const ERROR_PIPE_BUSY: i32 = 231;
    const RETRY_INTERVAL: std::time::Duration = std::time::Duration::from_millis(10);

    let deadline = tokio::time::Instant::now()
        .checked_add(timeout)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "timeout is out of range"))?;
    loop {
        match ClientOptions::new()
            .read(true)
            .write(true)
            .open(endpoint.as_pipe_name())
        {
            Ok(client) => return Ok(LocalStream(PipeStream::Client(client))),
            Err(error) if error.raw_os_error() == Some(ERROR_PIPE_BUSY) => {
                if tokio::time::Instant::now() >= deadline {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "local named-pipe connection timed out",
                    ));
                }
                tokio::time::sleep(RETRY_INTERVAL).await;
            }
            Err(error) => return Err(error),
        }
    }
}

fn create_server(pipe_name: &str, first_instance: bool) -> io::Result<NamedPipeServer> {
    let mut options = ServerOptions::new();
    options
        .access_inbound(true)
        .access_outbound(true)
        .first_pipe_instance(first_instance)
        .reject_remote_clients(true);
    windows_security::create_current_user_only(&options, pipe_name)
}
