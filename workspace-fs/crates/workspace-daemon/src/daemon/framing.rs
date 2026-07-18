fn failure(request: &Request, code: &str, message: &str) -> Response {
    Response {
        request_id: request.request_id.clone(),
        ok: false,
        result: None,
        error: Some(ProtocolError {
            code: code.into(),
            operation: request.operation.name().into(),
            workspace_id: workspace_id(&request.operation),
            message: message.into(),
        }),
    }
}

fn workspace_id(operation: &Operation) -> Option<String> {
    match operation {
        Operation::ApplyPolicy { session_id, .. }
        | Operation::MountWorkspace { session_id }
        | Operation::Prefetch { session_id, .. }
        | Operation::GetChangeJournal { session_id }
        | Operation::GetWorkspaceStatus { session_id }
        | Operation::ReadFileSummary { session_id, .. }
        | Operation::CommitCheckpoint { session_id, .. }
        | Operation::UnmountWorkspace { session_id }
        | Operation::CloseWorkspace { session_id }
        | Operation::DestroyEphemeralWorkspace { session_id } => Some(session_id.clone()),
        _ => None,
    }
}

fn read_frame(reader: &mut impl Read) -> Result<Option<Request>> {
    let mut length = [0u8; 4];
    match reader.read_exact(&mut length) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(None),
        Err(error) => return Err(error.into()),
    }
    let length = u32::from_le_bytes(length) as usize;
    if length > 16 * 1024 * 1024 {
        bail!("protocol frame exceeds 16 MiB");
    }
    let mut payload = vec![0; length];
    reader.read_exact(&mut payload)?;
    serde_json::from_slice(&payload)
        .context("decode protocol request")
        .map(Some)
}

fn write_frame(writer: &mut impl Write, response: &Response) -> Result<()> {
    let payload = serde_json::to_vec(response)?;
    writer.write_all(&(payload.len() as u32).to_le_bytes())?;
    writer.write_all(&payload)?;
    writer.flush()?;
    Ok(())
}
