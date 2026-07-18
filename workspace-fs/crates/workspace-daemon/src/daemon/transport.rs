pub fn serve(root: &Path) -> Result<()> {
    let mut daemon = Daemon::open(root)?;
    let mut input = std::io::stdin().lock();
    let mut output = std::io::stdout().lock();
    loop {
        let Some(request) = read_frame(&mut input)? else {
            break;
        };
        let shutdown = matches!(request.operation, Operation::Shutdown);
        let response = daemon.handle(request);
        write_frame(&mut output, &response)?;
        if shutdown {
            break;
        }
    }
    Ok(())
}

pub fn serve_socket(root: &Path) -> Result<()> {
    let mut daemon = Daemon::open(root)?;
    let listener = crate::local_socket::LocalListener::bind(root)
        .context("bind workspace daemon local transport")?;
    loop {
        let mut stream = listener.accept().context("accept daemon local client")?;
        if serve_connection(&mut daemon, &mut stream)? {
            return Ok(());
        }
    }
}

fn serve_connection(
    daemon: &mut Daemon,
    stream: &mut crate::local_socket::LocalStream,
) -> Result<bool> {
    let Some(request) = read_frame(stream)? else {
        return Ok(false);
    };
    let shutdown = matches!(request.operation, Operation::Shutdown);
    let response = daemon.handle(request);
    write_frame(stream, &response)?;
    Ok(shutdown)
}
