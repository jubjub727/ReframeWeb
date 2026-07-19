use std::time::Duration;

use prost::Message as _;
use reframe_store_protocol::wire::Envelope;
use reframe_store_transport::{
    FrameError, FrameReader, FrameWriter, decode_envelope, encode_envelope, encode_frame,
};
use tokio::io::{AsyncWriteExt as _, duplex};

fn envelope(id: &str) -> Envelope {
    Envelope {
        request_id: id.to_owned(),
        ..Envelope::default()
    }
}

#[test]
fn helpers_encode_a_big_endian_length_and_round_trip_payload() {
    let envelope = envelope("big-endian");
    let payload = encode_envelope(&envelope, 1024).unwrap();
    let frame = encode_frame(&envelope, 1024).unwrap();

    assert_eq!(&frame[..4], &(envelope.encoded_len() as u32).to_be_bytes());
    assert_eq!(&frame[4..], payload.as_ref());
    assert_eq!(decode_envelope(payload).unwrap(), envelope);
}

#[tokio::test]
async fn reads_fragmented_and_back_to_back_frames() {
    let first = encode_frame(&envelope("first"), 1024).unwrap();
    let second = encode_frame(&envelope("second"), 1024).unwrap();
    let (mut producer, consumer) = duplex(8);
    let producer_task = tokio::spawn(async move {
        for byte in first.iter().chain(second.iter()) {
            producer.write_all(&[*byte]).await.unwrap();
            tokio::task::yield_now().await;
        }
        producer.shutdown().await.unwrap();
    });

    let mut reader = FrameReader::new(consumer, 1024);
    assert_eq!(
        reader.read_envelope().await.unwrap(),
        Some(envelope("first"))
    );
    assert_eq!(
        reader.read_envelope().await.unwrap(),
        Some(envelope("second"))
    );
    assert_eq!(reader.read_envelope().await.unwrap(), None);
    producer_task.await.unwrap();
}

#[tokio::test]
async fn cancelled_read_keeps_partial_header_progress() {
    let frame = encode_frame(&envelope("resumes"), 1024).unwrap();
    let (mut producer, consumer) = duplex(64);
    producer.write_all(&frame[..2]).await.unwrap();

    let mut reader = FrameReader::new(consumer, 1024);
    assert!(
        tokio::time::timeout(Duration::from_millis(20), reader.read_envelope())
            .await
            .is_err()
    );
    producer.write_all(&frame[2..]).await.unwrap();
    assert_eq!(
        reader.read_envelope().await.unwrap(),
        Some(envelope("resumes"))
    );
}

#[tokio::test]
async fn rejects_oversized_frame_before_reading_payload() {
    let (mut producer, consumer) = duplex(16);
    producer.write_all(&9_u32.to_be_bytes()).await.unwrap();

    let mut reader = FrameReader::new(consumer, 8);
    let result = tokio::time::timeout(Duration::from_millis(100), reader.read_frame())
        .await
        .expect("size check must not wait for a payload");
    assert!(matches!(
        result,
        Err(FrameError::TooLarge {
            actual: 9,
            maximum: 8
        })
    ));
}

#[tokio::test]
async fn distinguishes_clean_eof_and_truncated_header() {
    let (mut producer, consumer) = duplex(16);
    producer.shutdown().await.unwrap();
    assert_eq!(
        FrameReader::new(consumer, 16).read_frame().await.unwrap(),
        None
    );

    let (mut producer, consumer) = duplex(16);
    producer.write_all(&[0, 0]).await.unwrap();
    producer.shutdown().await.unwrap();
    assert!(matches!(
        FrameReader::new(consumer, 16).read_frame().await,
        Err(FrameError::TruncatedHeader { received: 2 })
    ));
}

#[tokio::test]
async fn reports_truncated_payload_with_counts() {
    let (mut producer, consumer) = duplex(16);
    producer.write_all(&5_u32.to_be_bytes()).await.unwrap();
    producer.write_all(&[1, 2]).await.unwrap();
    producer.shutdown().await.unwrap();

    assert!(matches!(
        FrameReader::new(consumer, 16).read_frame().await,
        Err(FrameError::TruncatedPayload {
            expected: 5,
            received: 2
        })
    ));
}

#[tokio::test]
async fn rejects_malformed_protobuf_payload() {
    let (mut producer, consumer) = duplex(16);
    producer.write_all(&1_u32.to_be_bytes()).await.unwrap();
    producer.write_all(&[0x80]).await.unwrap();

    assert!(matches!(
        FrameReader::new(consumer, 16).read_envelope().await,
        Err(FrameError::Decode(_))
    ));
}

#[tokio::test]
async fn partial_frame_read_has_a_total_deadline() {
    let (mut producer, consumer) = duplex(16);
    producer.write_all(&[0]).await.unwrap();
    let mut reader = FrameReader::new(consumer, 16);

    assert!(matches!(
        reader
            .read_frame_with_timeout(Duration::from_millis(20))
            .await,
        Err(FrameError::ReadTimedOut { .. })
    ));
}

#[tokio::test]
async fn timed_out_writer_cannot_resume_after_a_partial_frame() {
    let (_reader, writer) = duplex(1);
    let mut writer = FrameWriter::new(writer, 16);
    assert!(matches!(
        writer
            .write_frame_with_timeout([1, 2], Duration::from_millis(20))
            .await,
        Err(FrameError::WriteTimedOut { .. })
    ));
    assert!(writer.is_poisoned());
    assert!(matches!(
        writer.write_frame([3]).await,
        Err(FrameError::WriterPoisoned)
    ));
}
