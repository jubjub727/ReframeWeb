use std::fmt;
use std::io::{self, Read, Write};

use anyhow::{Result, bail};
use serde_json::Value;

use crate::protocol::{MAX_FRAME_BYTES, ProtocolError, Request, Response, error_code};

#[derive(Debug)]
pub(super) enum ReadFrameError {
    Transport(io::Error),
    Client {
        code: &'static str,
        request_id: String,
        operation: String,
        workspace_id: Option<String>,
        message: String,
    },
}

impl ReadFrameError {
    pub(super) fn client_response(&self) -> Option<Response> {
        let Self::Client {
            code,
            request_id,
            operation,
            workspace_id,
            message,
        } = self
        else {
            return None;
        };
        Some(Response {
            request_id: request_id.clone(),
            ok: false,
            result: None,
            error: Some(ProtocolError {
                code: (*code).into(),
                operation: operation.clone(),
                workspace_id: workspace_id.clone(),
                message: message.clone(),
            }),
        })
    }

    pub(super) fn stream_is_synchronized(&self) -> bool {
        matches!(
            self,
            Self::Client { code, .. }
                if *code != error_code::FRAME_TOO_LARGE
        )
    }
}

impl fmt::Display for ReadFrameError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => error.fmt(formatter),
            Self::Client { code, message, .. } => write!(formatter, "{code}: {message}"),
        }
    }
}

impl std::error::Error for ReadFrameError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Transport(error) => Some(error),
            Self::Client { .. } => None,
        }
    }
}

impl From<io::Error> for ReadFrameError {
    fn from(error: io::Error) -> Self {
        Self::Transport(error)
    }
}

pub(super) fn read_frame(
    reader: &mut impl Read,
) -> std::result::Result<Option<Request>, ReadFrameError> {
    let Some(length) = read_frame_length(reader)? else {
        return Ok(None);
    };
    if length > MAX_FRAME_BYTES {
        return Err(ReadFrameError::Client {
            code: error_code::FRAME_TOO_LARGE,
            request_id: "unknown".into(),
            operation: "unknown".into(),
            workspace_id: None,
            message: format!("protocol frame exceeds {MAX_FRAME_BYTES} bytes"),
        });
    }
    let mut payload = vec![0; length];
    reader.read_exact(&mut payload)?;
    let value: Value = serde_json::from_slice(&payload).map_err(|_| ReadFrameError::Client {
        code: error_code::INVALID_JSON,
        request_id: "unknown".into(),
        operation: "unknown".into(),
        workspace_id: None,
        message: "request payload is not valid JSON".into(),
    })?;
    let request_id = string_field(&value, "request_id")
        .unwrap_or("unknown")
        .to_owned();
    let operation = string_field(&value, "operation")
        .unwrap_or("unknown")
        .to_owned();
    let workspace_id = string_field(&value, "session_id").map(str::to_owned);
    serde_json::from_value(value)
        .map(Some)
        .map_err(|_| ReadFrameError::Client {
            code: error_code::INVALID_REQUEST,
            request_id,
            operation,
            workspace_id,
            message: "request payload does not match the protocol schema".into(),
        })
}

fn read_frame_length(reader: &mut impl Read) -> std::result::Result<Option<usize>, ReadFrameError> {
    let mut length = [0u8; 4];
    loop {
        match reader.read(&mut length[..1]) {
            Ok(0) => return Ok(None),
            Ok(1) => break,
            Ok(_) => unreachable!("single-byte read returned more than one byte"),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error.into()),
        }
    }
    reader.read_exact(&mut length[1..])?;
    Ok(Some(u32::from_le_bytes(length) as usize))
}

fn string_field<'a>(value: &'a Value, field: &str) -> Option<&'a str> {
    value.as_object()?.get(field)?.as_str()
}

pub(super) fn encode_response(response: &Response) -> Result<String> {
    encode_response_with_limit(response, MAX_FRAME_BYTES)
}

pub(super) fn encode_response_with_limit(response: &Response, max_bytes: usize) -> Result<String> {
    let payload = serde_json::to_string(response)?;
    if payload.len() > max_bytes {
        bail!("protocol response exceeds {max_bytes} bytes");
    }
    Ok(payload)
}

pub(super) fn write_frame(writer: &mut impl Write, response: &Response) -> Result<()> {
    let payload = encode_response(response)?;
    writer.write_all(&(payload.len() as u32).to_le_bytes())?;
    writer.write_all(payload.as_bytes())?;
    writer.flush()?;
    Ok(())
}
