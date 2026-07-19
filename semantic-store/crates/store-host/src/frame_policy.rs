use std::collections::HashMap;

use prost::Message as _;
use reframe_store_catalog::{
    DEFAULT_INSPECTION_BYTE_BUDGET, DEFAULT_LIST_BYTE_BUDGET, MAX_INSPECTION_BYTE_BUDGET,
    MAX_PAGE_LIMIT,
};
use reframe_store_package::VerifiedPackage;
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    package::CapabilityKind,
    wire::{
        CatalogHit, Envelope, GetSchemaBundleResponse, GetStoreCardResponse, OpenStoreResponse,
        envelope, get_schema_bundle_response,
    },
};
use reframe_store_runtime::RuntimeConfig;
use thiserror::Error;

const UUID_TEXT: &str = "00000000-0000-4000-8000-000000000000";
const INVOCATION_ENVELOPE_HEADROOM: usize = 1_024;
const EMBEDDED_MESSAGE_HEADROOM: usize = 7;
// Cursor + revision fields, plus a worst-case length delimiter for every hit.
const LIST_RESPONSE_HEADROOM: usize = 256 + MAX_PAGE_LIMIT * EMBEDDED_MESSAGE_HEADROOM;

/// Cross-layer proof that every unbudgeted host response fits one transport frame.
#[derive(Clone, Debug)]
pub(crate) struct FramePolicy {
    maximum: usize,
}

impl FramePolicy {
    pub(crate) fn new(
        runtime: &RuntimeConfig,
        maximum: usize,
    ) -> Result<Self, FrameCompatibilityError> {
        let policy = Self { maximum };
        policy.require(
            runtime
                .max_component_event_bytes()
                .saturating_add(INVOCATION_ENVELOPE_HEADROOM),
            "the configured component-event limit",
        )?;
        Ok(policy)
    }

    pub(crate) fn validate_package(
        &self,
        package: &VerifiedPackage,
    ) -> Result<(), FrameCompatibilityError> {
        self.require(
            response_envelope(envelope::Message::GetSchemaBundleResponse(
                GetSchemaBundleResponse {
                    artifact_hash: vec![0; 32],
                    result: Some(get_schema_bundle_response::Result::DescriptorSet(
                        package.schema_bytes().to_vec(),
                    )),
                },
            ))
            .encoded_len(),
            "a Store schema bundle",
        )?;
        self.require(store_card_size(package), "a Store card")?;
        self.require(open_response_size(package), "an OpenStore response")
    }

    /// Restricts caller-selected projection work to the payload capacity left
    /// after the response envelope and deterministic catalog metadata.
    pub(crate) fn constrain_request(&self, request: &mut Envelope) {
        let body_capacity = self.response_body_capacity(request);
        let list_capacity = body_capacity.saturating_sub(LIST_RESPONSE_HEADROOM).max(1);
        let inspection_capacity = body_capacity.clamp(1, MAX_INSPECTION_BYTE_BUDGET);

        let Some(message) = request.message.as_mut() else {
            return;
        };
        match message {
            envelope::Message::SearchCatalogRequest(value) => {
                constrain_budget(
                    &mut value.byte_budget,
                    DEFAULT_LIST_BYTE_BUDGET,
                    list_capacity,
                );
            }
            envelope::Message::BrowseCatalogRequest(value) => {
                constrain_budget(
                    &mut value.byte_budget,
                    DEFAULT_LIST_BYTE_BUDGET,
                    list_capacity,
                );
            }
            envelope::Message::InspectCapabilityRequest(value) => {
                constrain_budget(
                    &mut value.byte_budget,
                    DEFAULT_INSPECTION_BYTE_BUDGET,
                    inspection_capacity,
                );
            }
            envelope::Message::InspectTypeRequest(value) => {
                constrain_budget(
                    &mut value.byte_budget,
                    DEFAULT_INSPECTION_BYTE_BUDGET,
                    inspection_capacity,
                );
            }
            _ => {}
        }
    }

    fn response_body_capacity(&self, request: &Envelope) -> usize {
        let metadata = Envelope {
            protocol_version: request.protocol_version,
            session_id: request.session_id.clone(),
            request_id: request.request_id.clone(),
            sequence_number: 0,
            message: None,
        }
        .encoded_len();
        self.maximum
            .saturating_sub(metadata)
            .saturating_sub(EMBEDDED_MESSAGE_HEADROOM)
    }

    fn require(
        &self,
        required: usize,
        requirement: &'static str,
    ) -> Result<(), FrameCompatibilityError> {
        if required > self.maximum {
            return Err(FrameCompatibilityError {
                configured: self.maximum,
                required,
                requirement,
            });
        }
        Ok(())
    }
}

fn constrain_budget(value: &mut u32, default: usize, maximum: usize) {
    let requested = if *value == 0 {
        default
    } else {
        usize::try_from(*value).unwrap_or(usize::MAX)
    };
    *value = u32::try_from(requested.min(maximum)).expect("transport frames are u32-bounded");
}

fn store_card_size(package: &VerifiedPackage) -> usize {
    let catalog = package.catalog();
    let entries: HashMap<_, _> = catalog
        .entries
        .iter()
        .map(|entry| (entry.id.as_str(), entry))
        .collect();
    let top_level_topics = catalog
        .top_level_topic_ids
        .iter()
        .map(|id| {
            entries
                .get(id.as_str())
                .expect("verified top-level topics exist")
        })
        .map(|entry| CatalogHit {
            id: entry.id.clone(),
            kind: CapabilityKind::Topic as i32,
            title: entry.title.clone(),
            summary: entry.summary.clone(),
        })
        .collect();
    response_envelope(envelope::Message::GetStoreCardResponse(
        GetStoreCardResponse {
            store_id: catalog.store_id.clone(),
            display_name: catalog.display_name.clone(),
            overview_sentences: catalog.overview_sentences.iter().take(2).cloned().collect(),
            top_level_topics,
            semantic_interface_version: catalog.semantic_interface_version,
            catalog_revision: package.catalog_revision().to_vec(),
        },
    ))
    .encoded_len()
}

fn open_response_size(package: &VerifiedPackage) -> usize {
    response_envelope(envelope::Message::OpenStoreResponse(OpenStoreResponse {
        store_id: package.manifest().store_id.clone(),
        negotiated_protocol_version: Some(CURRENT_PROTOCOL_VERSION),
        semantic_interface_version: package.manifest().semantic_interface_version,
        catalog_revision: package.catalog_revision().to_vec(),
    }))
    .encoded_len()
}

fn response_envelope(message: envelope::Message) -> Envelope {
    Envelope {
        protocol_version: Some(CURRENT_PROTOCOL_VERSION),
        session_id: UUID_TEXT.to_owned(),
        request_id: UUID_TEXT.to_owned(),
        sequence_number: u64::MAX,
        message: Some(message),
    }
}

#[derive(Clone, Debug, Eq, Error, PartialEq)]
#[error(
    "transport frame limit is {configured} bytes, but {requirement} requires at least {required} bytes"
)]
pub struct FrameCompatibilityError {
    configured: usize,
    required: usize,
    requirement: &'static str,
}

impl FrameCompatibilityError {
    #[must_use]
    pub const fn configured(&self) -> usize {
        self.configured
    }

    #[must_use]
    pub const fn required(&self) -> usize {
        self.required
    }

    #[must_use]
    pub const fn requirement(&self) -> &'static str {
        self.requirement
    }
}

#[cfg(test)]
mod tests {
    use reframe_store_protocol::wire::{InspectCapabilityRequest, envelope};

    use super::*;

    #[test]
    fn inspection_budget_is_capped_to_the_actual_frame_payload() {
        let runtime = RuntimeConfig::default()
            .with_max_component_event_bytes(1_024)
            .unwrap();
        let policy = FramePolicy::new(&runtime, 4 * 1024).unwrap();
        let mut request = response_envelope(envelope::Message::InspectCapabilityRequest(
            InspectCapabilityRequest {
                byte_budget: u32::MAX,
                ..InspectCapabilityRequest::default()
            },
        ));

        policy.constrain_request(&mut request);

        let envelope::Message::InspectCapabilityRequest(request) = request.message.unwrap() else {
            panic!("request kind changed")
        };
        assert!(usize::try_from(request.byte_budget).unwrap() < policy.maximum);
        assert!(usize::try_from(request.byte_budget).unwrap() <= MAX_INSPECTION_BYTE_BUDGET);
    }

    #[test]
    fn list_budget_reserves_cursor_and_repeated_item_overhead() {
        let runtime = RuntimeConfig::default()
            .with_max_component_event_bytes(1_024)
            .unwrap();
        let policy = FramePolicy::new(&runtime, 4 * 1024).unwrap();
        let mut request = response_envelope(envelope::Message::SearchCatalogRequest(
            reframe_store_protocol::wire::SearchCatalogRequest {
                byte_budget: u32::MAX,
                ..Default::default()
            },
        ));

        policy.constrain_request(&mut request);

        let envelope::Message::SearchCatalogRequest(request) = request.message.unwrap() else {
            panic!("request kind changed")
        };
        let budget = usize::try_from(request.byte_budget).unwrap();
        assert!(budget + LIST_RESPONSE_HEADROOM + EMBEDDED_MESSAGE_HEADROOM < policy.maximum);
    }
}
