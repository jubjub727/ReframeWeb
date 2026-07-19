use std::future;

use anyhow::{Context, Result, ensure};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::oneshot,
    task::JoinHandle,
};

pub(crate) async fn quick_server(body: &'static [u8]) -> Result<(String, JoinHandle<Result<()>>)> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let task = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await?;
        read_headers(&mut stream).await?;
        let headers = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream.write_all(headers.as_bytes()).await?;
        stream.write_all(body).await?;
        stream.shutdown().await?;
        Ok(())
    });
    Ok((format!("http://{address}/value"), task))
}

pub(crate) async fn slow_server() -> Result<(String, oneshot::Receiver<()>, JoinHandle<Result<()>>)>
{
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (accepted_sender, accepted) = oneshot::channel();
    let task = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await?;
        read_headers(&mut stream).await?;
        let _ = accepted_sender.send(());
        future::pending::<()>().await;
        Ok(())
    });
    Ok((format!("http://{address}/slow"), accepted, task))
}

pub(crate) async fn controlled_server(
    body: &'static [u8],
) -> Result<(
    String,
    oneshot::Receiver<()>,
    oneshot::Sender<()>,
    JoinHandle<Result<()>>,
)> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (accepted_sender, accepted) = oneshot::channel();
    let (release, released) = oneshot::channel();
    let task = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await?;
        read_headers(&mut stream).await?;
        let _ = accepted_sender.send(());
        let _ = released.await;
        let headers = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream.write_all(headers.as_bytes()).await?;
        stream.write_all(body).await?;
        stream.shutdown().await?;
        Ok(())
    });
    Ok((
        format!("http://{address}/controlled"),
        accepted,
        release,
        task,
    ))
}

async fn read_headers(stream: &mut TcpStream) -> Result<()> {
    const MAX_HEADERS: usize = 16 * 1024;
    let mut received = Vec::new();
    let mut chunk = [0_u8; 1024];
    while !received.windows(4).any(|window| window == b"\r\n\r\n") {
        let count = stream
            .read(&mut chunk)
            .await
            .context("could not read loopback HTTP request")?;
        ensure!(count != 0, "loopback HTTP request ended before its headers");
        received.extend_from_slice(&chunk[..count]);
        ensure!(
            received.len() <= MAX_HEADERS,
            "loopback HTTP headers are too large"
        );
    }
    Ok(())
}
