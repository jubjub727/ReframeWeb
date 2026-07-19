use std::sync::Arc;

use prost::Message;
use reframe_store_catalog::{CatalogError, InvocationContract};
use reframe_store_protocol::wire::{
    ComponentInvocationRequest, FailureCode, InvocationEvent, invocation_event,
};
use thiserror::Error;

use crate::{CompiledComponent, ComponentError, LoadedStore, invocation::InvocationOutput};

pub(crate) async fn run_invocation(
    store: Arc<LoadedStore>,
    request: ComponentInvocationRequest,
    contract: InvocationContract,
    output: &tokio::sync::Mutex<InvocationOutput>,
    maximum_event_bytes: usize,
) {
    if let Err(error) = drive(
        store.component(),
        &store,
        request,
        &contract,
        output,
        maximum_event_bytes,
    )
    .await
    {
        tracing::warn!(
            store_id = %store.package().manifest().store_id,
            capability_id = %contract.capability_id(),
            %error,
            "Semantic Store invocation failed"
        );
        let mut output = output.lock().await;
        if let Err(delivery) = output
            .fail(FailureCode::Internal, error.client_message())
            .await
        {
            tracing::debug!(%delivery, "invocation failure could not be delivered");
        }
    }
}

async fn drive(
    component: &CompiledComponent,
    store: &LoadedStore,
    request: ComponentInvocationRequest,
    contract: &InvocationContract,
    output: &tokio::sync::Mutex<InvocationOutput>,
    maximum_event_bytes: usize,
) -> Result<(), InvocationRunError> {
    let mut invocation = component.invoke(request.encode_to_vec()).await?;
    loop {
        let bytes = invocation
            .next()
            .await?
            .ok_or(InvocationRunError::PrematureEnd)?;
        if bytes.len() > maximum_event_bytes {
            return Err(InvocationRunError::EventTooLarge {
                actual: bytes.len(),
                maximum: maximum_event_bytes,
            });
        }
        let event = InvocationEvent::decode(bytes.as_slice())?;
        output.lock().await.validate_candidate(&event)?;
        validate_output(store, contract, &event)?;

        let terminal = matches!(
            event.event,
            Some(invocation_event::Event::Complete(_) | invocation_event::Event::Failure(_))
        );
        if terminal {
            match invocation.next().await? {
                None => {
                    output.lock().await.send_guest(event).await?;
                    return Ok(());
                }
                Some(_) => return Err(InvocationRunError::EventAfterTerminal),
            }
        }
        output.lock().await.send_guest(event).await?;
    }
}

fn validate_output(
    store: &LoadedStore,
    contract: &InvocationContract,
    event: &InvocationEvent,
) -> Result<(), InvocationRunError> {
    if let Some(invocation_event::Event::Data(data)) = &event.event {
        let value = data.value.as_ref().ok_or(InvocationRunError::MissingData)?;
        store.catalog().validate_output(contract, value)?;
    }
    Ok(())
}

#[derive(Debug, Error)]
enum InvocationRunError {
    #[error(transparent)]
    Component(#[from] ComponentError),
    #[error("component event is not a valid InvocationEvent")]
    Decode(#[from] prost::DecodeError),
    #[error(transparent)]
    Catalog(#[from] CatalogError),
    #[error(transparent)]
    Output(#[from] super::output::InvocationOutputError),
    #[error("component event stream ended before a terminal event")]
    PrematureEnd,
    #[error("component emitted an event after its terminal event")]
    EventAfterTerminal,
    #[error("component emitted a Data event without a value")]
    MissingData,
    #[error("component event has {actual} bytes, exceeding the {maximum}-byte limit")]
    EventTooLarge { actual: usize, maximum: usize },
}

impl InvocationRunError {
    fn client_message(&self) -> &'static str {
        match self {
            Self::Component(_) => "Store component execution failed",
            Self::Decode(_)
            | Self::Catalog(_)
            | Self::Output(_)
            | Self::PrematureEnd
            | Self::EventAfterTerminal
            | Self::MissingData
            | Self::EventTooLarge { .. } => "Store component violated the invocation contract",
        }
    }
}
