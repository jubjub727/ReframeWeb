use anyhow::{Context, Result, bail, ensure};
use reframe_reference_store::NORMALIZE_LABEL_FUNCTION_ID;
use reframe_store_protocol::{
    package::CapabilityKind,
    wire::{
        BrowseCatalogRequest, GetSchemaBundleRequest, InspectTypeRequest, envelope,
        get_schema_bundle_response,
    },
};

use super::TestClient;

pub(crate) async fn browse_and_inspect_schema(
    client: &mut TestClient,
    session_id: &str,
) -> Result<()> {
    browse_function_topic(client, session_id).await?;
    inspect_function_input(client, session_id).await?;
    read_schema_once(client, session_id).await
}

async fn browse_function_topic(client: &mut TestClient, session_id: &str) -> Result<()> {
    let response = client
        .request(
            session_id,
            envelope::Message::BrowseCatalogRequest(BrowseCatalogRequest {
                parent_topic_id: "reference.text".to_owned(),
                kinds: vec![CapabilityKind::Function as i32],
                limit: 10,
                byte_budget: 8 * 1024,
                cursor: String::new(),
            }),
        )
        .await?;
    match response.message {
        Some(envelope::Message::BrowseCatalogResponse(browse)) => ensure!(
            browse.entries.len() == 1
                && browse.entries[0].id == NORMALIZE_LABEL_FUNCTION_ID
                && browse.next_cursor.is_empty(),
            "BrowseCatalog did not return the immediate function child"
        ),
        _ => bail!("BrowseCatalog did not return BrowseCatalogResponse"),
    }
    Ok(())
}

async fn inspect_function_input(client: &mut TestClient, session_id: &str) -> Result<()> {
    let response = client
        .request(
            session_id,
            envelope::Message::InspectTypeRequest(InspectTypeRequest {
                type_name: "reframe.examples.reference.v1.NormalizeLabelInput".to_owned(),
                field_paths: vec!["label".to_owned()],
                depth: 1,
                byte_budget: u32::MAX,
            }),
        )
        .await?;
    match response.message {
        Some(envelope::Message::InspectTypeResponse(inspect)) => {
            let view = inspect
                .r#type
                .context("InspectType omitted its type view")?;
            ensure!(
                view.full_name == "reframe.examples.reference.v1.NormalizeLabelInput",
                "InspectType returned the wrong message"
            );
            ensure!(
                view.fields.len() == 1 && view.fields[0].name == "label",
                "InspectType did not honor its field projection"
            );
        }
        _ => bail!("InspectType did not return InspectTypeResponse"),
    }
    Ok(())
}

async fn read_schema_once(client: &mut TestClient, session_id: &str) -> Result<()> {
    let response = client
        .request(
            session_id,
            envelope::Message::GetSchemaBundleRequest(GetSchemaBundleRequest {
                known_artifact_hash: Vec::new(),
            }),
        )
        .await?;
    let Some(envelope::Message::GetSchemaBundleResponse(schema)) = response.message else {
        bail!("GetSchemaBundle did not return GetSchemaBundleResponse");
    };
    ensure!(
        schema.artifact_hash.len() == 32,
        "schema artifact hash is not SHA-256"
    );
    ensure!(
        matches!(
            schema.result,
            Some(get_schema_bundle_response::Result::DescriptorSet(ref bytes)) if !bytes.is_empty()
        ),
        "the first schema request did not return descriptor bytes"
    );

    let unchanged = client
        .request(
            session_id,
            envelope::Message::GetSchemaBundleRequest(GetSchemaBundleRequest {
                known_artifact_hash: schema.artifact_hash,
            }),
        )
        .await?;
    ensure!(
        matches!(
            unchanged.message,
            Some(envelope::Message::GetSchemaBundleResponse(response))
                if matches!(response.result, Some(get_schema_bundle_response::Result::Unchanged(true)))
        ),
        "a known schema artifact was transferred again"
    );
    Ok(())
}
