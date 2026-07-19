use prost::Message;
use reframe_reference_store::{
    HttpClient, HttpScheme, HttpSnapshot, HttpSnapshotSelector, HttpTarget, ResourceError,
    invoke_with_http,
};
use reframe_store_protocol::wire::{
    ComponentInvocationRequest, InvocationEvent, ReadResourceRequest, component_invocation_request,
    invocation_event,
};
use reframe_store_sdk::{pack, unpack};

struct HttpsFixture;

impl HttpClient for HttpsFixture {
    fn get(&self, target: &HttpTarget) -> Result<HttpSnapshot, ResourceError> {
        assert_eq!(target.scheme(), HttpScheme::Https);
        assert_eq!(target.authority(), "example.com");
        Ok(HttpSnapshot {
            url: target.url().to_owned(),
            status_code: 200,
            content_type: "text/plain".to_owned(),
            body: b"bounded https".to_vec(),
        })
    }
}

#[test]
fn general_snapshot_accepts_an_ordinary_https_url() {
    let request = ComponentInvocationRequest {
        request_id: "08574704-e61f-4135-964f-f78f39599f7d".to_owned(),
        operation: Some(component_invocation_request::Operation::ReadResource(
            ReadResourceRequest {
                resource_id: "reference.http.snapshot".to_owned(),
                selector: Some(
                    pack(&HttpSnapshotSelector {
                        url: "https://example.com/status?q=1".to_owned(),
                        max_body_bytes: 4096,
                    })
                    .unwrap(),
                ),
            },
        )),
    };
    let invocation = invoke_with_http(&request.encode_to_vec(), HttpsFixture).unwrap();
    let events = std::iter::from_fn(|| invocation.next().unwrap())
        .map(|bytes| InvocationEvent::decode(bytes.as_slice()).unwrap())
        .collect::<Vec<_>>();
    let value = events
        .iter()
        .find_map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Data(data)) => data.value.as_ref(),
            _ => None,
        })
        .expect("HTTP snapshot data");
    let snapshot = unpack::<HttpSnapshot>(value).unwrap();

    assert_eq!(snapshot.status_code, 200);
    assert_eq!(snapshot.body, b"bounded https");
    assert!(matches!(
        events.last().and_then(|event| event.event.as_ref()),
        Some(invocation_event::Event::Complete(_))
    ));
}
