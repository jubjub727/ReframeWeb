use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION, parse_uuid,
    wire::{Envelope, ProtocolVersion, envelope},
};

pub(super) struct ReplyMetadata {
    protocol: ProtocolVersion,
    request_id: String,
    session_id: String,
}

impl ReplyMetadata {
    pub(super) fn for_request(request: &Envelope) -> Self {
        let protocol = request
            .protocol_version
            .as_ref()
            .filter(|version| version.ensure_supported().is_ok())
            .cloned()
            .unwrap_or(CURRENT_PROTOCOL_VERSION);
        let request_id = parse_uuid("request_id", &request.request_id)
            .map(|value| value.to_string())
            .unwrap_or_else(|_| uuid::Uuid::new_v4().to_string());
        let session_id = parse_uuid("session_id", &request.session_id)
            .map(|value| value.to_string())
            .unwrap_or_default();
        Self {
            protocol,
            request_id,
            session_id,
        }
    }

    pub(super) fn envelope(&self, message: envelope::Message) -> Envelope {
        Envelope {
            protocol_version: Some(self.protocol),
            session_id: self.session_id.clone(),
            request_id: self.request_id.clone(),
            sequence_number: 0,
            message: Some(message),
        }
    }
}
