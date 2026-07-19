use anyhow::{Result, bail, ensure};
use reframe_reference_store::STORE_ID;
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    wire::{
        Envelope, ErrorCode, GetStoreCardRequest, InspectCapabilityRequest, InspectionSection,
        InterfaceRequirement, OpenStoreRequest, SearchCatalogRequest, envelope,
    },
};

use super::TestClient;

pub(crate) async fn open_and_inspect(client: &mut TestClient) -> Result<String> {
    let response = request_open(client).await?;
    let session_id = response.session_id;
    ensure!(!session_id.is_empty(), "OpenStore did not bind a session");
    match response.message {
        Some(envelope::Message::OpenStoreResponse(open)) => {
            ensure!(open.store_id == STORE_ID, "OpenStore bound the wrong Store");
        }
        _ => bail!("OpenStore did not return OpenStoreResponse"),
    }

    let card = client
        .request(
            &session_id,
            envelope::Message::GetStoreCardRequest(GetStoreCardRequest {}),
        )
        .await?;
    match card.message {
        Some(envelope::Message::GetStoreCardResponse(card)) => {
            ensure!(card.store_id == STORE_ID, "Store card has the wrong ID");
            ensure!(
                card.overview_sentences.len() == 2,
                "Store card is not minimal"
            );
            ensure!(
                card.top_level_topics.len() == 4,
                "Store card topics are incomplete"
            );
        }
        _ => bail!("GetStoreCard did not return GetStoreCardResponse"),
    }

    let search = client
        .request(
            &session_id,
            envelope::Message::SearchCatalogRequest(SearchCatalogRequest {
                query: "fetch a localhost HTTP endpoint".to_owned(),
                kinds: Vec::new(),
                topic_id: String::new(),
                limit: 5,
                byte_budget: 8 * 1024,
                cursor: String::new(),
            }),
        )
        .await?;
    match search.message {
        Some(envelope::Message::SearchCatalogResponse(search)) => ensure!(
            search
                .hits
                .iter()
                .any(|hit| hit.id == "reference.http.loopback_snapshot"),
            "bounded search did not find the HTTP resource"
        ),
        _ => bail!("SearchCatalog did not return SearchCatalogResponse"),
    };

    let rejected = client
        .request(
            &session_id,
            envelope::Message::InspectCapabilityRequest(InspectCapabilityRequest {
                capability_id: "x".repeat(1024 * 1024),
                byte_budget: u32::MAX,
                ..InspectCapabilityRequest::default()
            }),
        )
        .await?;
    match rejected.message {
        Some(envelope::Message::Error(error)) => {
            ensure!(
                error.code == ErrorCode::InvalidEnvelope as i32,
                "oversized identifier returned the wrong protocol fault"
            );
            ensure!(
                error.message.len() < 256,
                "protocol fault echoed attacker-controlled input"
            );
        }
        _ => bail!("oversized identifier was not rejected"),
    }

    let inspect = client
        .request(
            &session_id,
            envelope::Message::InspectCapabilityRequest(InspectCapabilityRequest {
                capability_id: "reference.http.loopback_snapshot".to_owned(),
                sections: vec![
                    InspectionSection::Summary as i32,
                    InspectionSection::Input as i32,
                    InspectionSection::Output as i32,
                ],
                schema_depth: 1,
                example_limit: 0,
                byte_budget: u32::MAX,
            }),
        )
        .await?;
    match inspect.message {
        Some(envelope::Message::InspectCapabilityResponse(inspect)) => {
            ensure!(inspect.summary.is_some(), "requested summary is missing");
            ensure!(inspect.input.is_some(), "requested input type is missing");
            ensure!(inspect.output.is_some(), "requested output type is missing");
            ensure!(inspect.when_to_use.is_none(), "unrequested guidance leaked");
            ensure!(inspect.examples.is_empty(), "unrequested examples leaked");
        }
        _ => bail!("InspectCapability did not return its response"),
    }
    Ok(session_id)
}

pub(crate) async fn request_open(client: &mut TestClient) -> Result<Envelope> {
    client
        .request(
            "",
            envelope::Message::OpenStoreRequest(OpenStoreRequest {
                store_id: STORE_ID.to_owned(),
                supported_protocol_version: Some(CURRENT_PROTOCOL_VERSION),
                required_interface: Some(InterfaceRequirement {
                    major: 1,
                    min_minor: 0,
                    max_minor: Some(0),
                }),
            }),
        )
        .await
}

pub(crate) async fn store_card_revision(
    client: &mut TestClient,
    session_id: &str,
) -> Result<Vec<u8>> {
    let response = client
        .request(
            session_id,
            envelope::Message::GetStoreCardRequest(GetStoreCardRequest {}),
        )
        .await?;
    match response.message {
        Some(envelope::Message::GetStoreCardResponse(card)) => Ok(card.catalog_revision),
        _ => bail!("GetStoreCard did not return GetStoreCardResponse"),
    }
}

pub(crate) async fn first_catalog_cursor(
    client: &mut TestClient,
    session_id: &str,
) -> Result<String> {
    let response = client
        .request(
            session_id,
            envelope::Message::SearchCatalogRequest(SearchCatalogRequest {
                limit: 1,
                byte_budget: 8 * 1024,
                ..SearchCatalogRequest::default()
            }),
        )
        .await?;
    match response.message {
        Some(envelope::Message::SearchCatalogResponse(search)) => {
            ensure!(
                !search.next_cursor.is_empty(),
                "the reference catalog is too small to exercise cursor invalidation"
            );
            Ok(search.next_cursor)
        }
        _ => bail!("SearchCatalog did not return SearchCatalogResponse"),
    }
}

pub(crate) async fn expect_stale_catalog_cursor(
    client: &mut TestClient,
    session_id: &str,
    cursor: String,
) -> Result<()> {
    let response = client
        .request(
            session_id,
            envelope::Message::SearchCatalogRequest(SearchCatalogRequest {
                limit: 1,
                byte_budget: 8 * 1024,
                cursor,
                ..SearchCatalogRequest::default()
            }),
        )
        .await?;
    ensure!(
        matches!(
            response.message,
            Some(envelope::Message::Error(error))
                if error.code == ErrorCode::StaleCursor as i32
        ),
        "a cursor from the previous Store revision was not reported as stale"
    );
    Ok(())
}
