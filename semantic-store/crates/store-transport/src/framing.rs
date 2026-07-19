mod reader;
mod writer;

use bytes::{BufMut, Bytes, BytesMut};
use prost::Message;
use reframe_store_protocol::wire::Envelope;
use tokio::io::{AsyncRead, AsyncWrite};

use crate::{FrameError, MAX_FRAME_SIZE};

pub use reader::FrameReader;
pub use writer::FrameWriter;

const HEADER_SIZE: usize = size_of::<u32>();

/// Encodes one protobuf message without its transport length prefix.
pub fn encode_message<M: Message>(message: &M, maximum: usize) -> Result<Bytes, FrameError> {
    let encoded_len = message.encoded_len();
    validate_length(encoded_len, maximum)?;
    let mut encoded = BytesMut::with_capacity(encoded_len);
    message.encode(&mut encoded)?;
    Ok(encoded.freeze())
}

/// Decodes one protobuf message from an already-delimited payload.
pub fn decode_message<M>(payload: impl AsRef<[u8]>) -> Result<M, FrameError>
where
    M: Message + Default,
{
    M::decode(payload.as_ref()).map_err(FrameError::from)
}

pub fn encode_envelope(envelope: &Envelope, maximum: usize) -> Result<Bytes, FrameError> {
    encode_message(envelope, maximum)
}

pub fn decode_envelope(payload: impl AsRef<[u8]>) -> Result<Envelope, FrameError> {
    decode_message(payload)
}

/// Encodes a complete wire frame (length prefix and protobuf payload).
pub fn encode_frame<M: Message>(message: &M, maximum: usize) -> Result<Bytes, FrameError> {
    let payload = encode_message(message, maximum)?;
    let length =
        u32::try_from(payload.len()).map_err(|_| FrameError::LengthOverflow(payload.len()))?;
    let mut frame = BytesMut::with_capacity(HEADER_SIZE + payload.len());
    frame.put_u32(length);
    frame.extend_from_slice(&payload);
    Ok(frame.freeze())
}

pub async fn read_frame<R>(reader: &mut R, maximum: usize) -> Result<Option<Bytes>, FrameError>
where
    R: AsyncRead + Unpin,
{
    FrameReader::new(reader, maximum).read_frame().await
}

pub async fn read_envelope<R>(
    reader: &mut R,
    maximum: usize,
) -> Result<Option<Envelope>, FrameError>
where
    R: AsyncRead + Unpin,
{
    FrameReader::new(reader, maximum).read_envelope().await
}

pub async fn write_frame<W>(
    writer: &mut W,
    payload: impl AsRef<[u8]>,
    maximum: usize,
) -> Result<(), FrameError>
where
    W: AsyncWrite + Unpin,
{
    FrameWriter::new(writer, maximum).write_frame(payload).await
}

pub async fn write_envelope<W>(
    writer: &mut W,
    envelope: &Envelope,
    maximum: usize,
) -> Result<(), FrameError>
where
    W: AsyncWrite + Unpin,
{
    FrameWriter::new(writer, maximum)
        .write_envelope(envelope)
        .await
}

fn validate_length(actual: usize, maximum: usize) -> Result<(), FrameError> {
    let maximum = maximum.min(MAX_FRAME_SIZE);
    if actual > u32::MAX as usize {
        return Err(FrameError::LengthOverflow(actual));
    }
    if actual > maximum {
        return Err(FrameError::TooLarge { actual, maximum });
    }
    Ok(())
}
