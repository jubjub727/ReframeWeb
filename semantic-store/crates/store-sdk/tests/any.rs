use prost::Message;
use prost_types::Any;
use reframe_store_protocol::MAX_TYPE_URL_BYTES;
use reframe_store_sdk::{AnyError, any_type_name, pack, unpack};

#[derive(Clone, PartialEq, Message)]
struct Sample {
    #[prost(string, tag = "1")]
    value: String,
}

impl prost::Name for Sample {
    const NAME: &'static str = "Sample";
    const PACKAGE: &'static str = "test.sdk";
}

#[test]
fn packs_and_unpacks_canonical_any_values() {
    let sample = Sample {
        value: "typed".to_owned(),
    };
    let packed = pack(&sample).unwrap();
    assert_eq!(packed.type_url, "type.googleapis.com/test.sdk.Sample");
    assert_eq!(unpack::<Sample>(&packed).unwrap(), sample);
}

#[test]
fn rejects_a_payload_declared_as_another_type() {
    let value = Any {
        type_url: "custom.invalid/test.sdk.Other".to_owned(),
        value: Vec::new(),
    };
    assert!(matches!(
        unpack::<Sample>(&value),
        Err(AnyError::TypeMismatch { .. })
    ));
}

#[test]
fn rejects_noncanonical_or_oversized_type_urls() {
    for type_url in [
        "test.sdk.Sample".to_owned(),
        "/test.sdk.Sample".to_owned(),
        "type.googleapis.com/".to_owned(),
        format!("type.googleapis.com/{}", "x".repeat(MAX_TYPE_URL_BYTES)),
    ] {
        assert!(matches!(
            any_type_name(&Any {
                type_url,
                value: Vec::new(),
            }),
            Err(AnyError::InvalidTypeUrl)
        ));
    }
}
