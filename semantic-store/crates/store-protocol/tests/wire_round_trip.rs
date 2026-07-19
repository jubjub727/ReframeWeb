use prost::Message;
use prost_types::{Any, FileDescriptorSet};
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION, descriptor_set_bytes,
    wire::{
        ComponentInvocationRequest, Envelope, GetStoreCardRequest, InterfaceRequirement,
        OpenStoreRequest, ProtocolVersion, ReadResourceRequest, component_invocation_request,
        envelope,
    },
};

const SESSION_ID: &str = "00000000-0000-4000-8000-000000000001";
const REQUEST_ID: &str = "00000000-0000-4000-8000-000000000002";
const CARD_REQUEST_HEX: &str = concat!(
    "0a0208011224",
    "30303030303030302d303030302d343030302d383030302d303030303030303030303031",
    "1a24",
    "30303030303030302d303030302d343030302d383030302d303030303030303030303032",
    "6200"
);

#[test]
fn envelope_matches_the_v1_golden_bytes_and_round_trips() {
    let envelope = Envelope {
        protocol_version: Some(CURRENT_PROTOCOL_VERSION),
        session_id: SESSION_ID.to_owned(),
        request_id: REQUEST_ID.to_owned(),
        sequence_number: 0,
        message: Some(envelope::Message::GetStoreCardRequest(
            GetStoreCardRequest {},
        )),
    };

    envelope.validate().expect("valid envelope");
    let bytes = envelope.encode_to_vec();
    assert_eq!(hex::encode(&bytes), CARD_REQUEST_HEX);
    assert_eq!(
        Envelope::decode(bytes.as_slice()).expect("decode"),
        envelope
    );
}

#[test]
fn component_requests_are_transport_independent_and_typed() {
    let request = ComponentInvocationRequest {
        request_id: REQUEST_ID.to_owned(),
        operation: Some(component_invocation_request::Operation::ReadResource(
            ReadResourceRequest {
                resource_id: "weather.current".to_owned(),
                selector: Some(Any {
                    type_url: "type.googleapis.com/weather.Selector".to_owned(),
                    value: vec![8, 1],
                }),
            },
        )),
    };

    request.validate().expect("valid component request");
    let encoded = request.encode_to_vec();
    assert_eq!(
        ComponentInvocationRequest::decode(encoded.as_slice()).expect("decode"),
        request
    );
}

#[test]
fn open_store_is_the_only_request_that_does_not_need_a_session() {
    let envelope = Envelope {
        protocol_version: Some(CURRENT_PROTOCOL_VERSION),
        session_id: String::new(),
        request_id: REQUEST_ID.to_owned(),
        sequence_number: 0,
        message: Some(envelope::Message::OpenStoreRequest(OpenStoreRequest {
            store_id: "dev.reframe.weather".to_owned(),
            supported_protocol_version: Some(ProtocolVersion { major: 1, minor: 3 }),
            required_interface: Some(InterfaceRequirement {
                major: 2,
                min_minor: 1,
                max_minor: Some(4),
            }),
        })),
    };

    envelope.validate().expect("valid negotiation envelope");
}

#[test]
fn embedded_descriptor_is_complete_and_keeps_source_info() {
    let set = FileDescriptorSet::decode(descriptor_set_bytes()).expect("descriptor set");
    let names: Vec<_> = set
        .file
        .iter()
        .filter_map(|file| file.name.as_deref())
        .collect();

    assert!(names.contains(&"wire.proto"));
    assert!(names.contains(&"package.proto"));
    assert!(names.contains(&"google/protobuf/any.proto"));
    assert!(set.file.iter().all(|file| file.source_code_info.is_some()));
}
