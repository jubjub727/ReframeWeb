use std::sync::Arc;

use thiserror::Error;
use wasmtime::component::{Component, ResourceAny};

use crate::{
    bindings::{SemanticStore, SemanticStorePre},
    engine::RuntimeEngine,
    host_state::HostState,
};

/// A component compilation, linkage, invocation, or guest-contract failure.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum ComponentError {
    #[error("Store component could not be compiled: {0}")]
    Compile(wasmtime::Error),
    #[error("Store component does not implement the Semantic Store world: {0}")]
    Link(wasmtime::Error),
    #[error("Store component trapped: {0}")]
    Trap(wasmtime::Error),
    #[error("Store component rejected the invocation: {0}")]
    Guest(String),
}

/// One compiled and pre-linked Store component.
///
/// The compilation is reusable, but [`invoke`](Self::invoke) always creates a
/// fresh Wasmtime store and component instance.
#[derive(Clone)]
pub struct CompiledComponent {
    engine: Arc<RuntimeEngine>,
    pre: SemanticStorePre<HostState>,
}

impl std::fmt::Debug for CompiledComponent {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("CompiledComponent")
            .finish_non_exhaustive()
    }
}

impl CompiledComponent {
    pub fn compile(engine: Arc<RuntimeEngine>, wasm: &[u8]) -> Result<Self, ComponentError> {
        let component =
            Component::from_binary(engine.engine(), wasm).map_err(ComponentError::Compile)?;
        let instance_pre = engine
            .linker()
            .instantiate_pre(&component)
            .map_err(ComponentError::Link)?;
        let pre = SemanticStorePre::new(instance_pre).map_err(ComponentError::Link)?;
        Ok(Self { engine, pre })
    }

    pub async fn invoke(&self, request: Vec<u8>) -> Result<ComponentInvocation, ComponentError> {
        let mut store = self.engine.new_store();
        let bindings = self
            .pre
            .instantiate_async(&mut store)
            .await
            .map_err(ComponentError::Trap)?;
        let invocation = bindings
            .reframe_semantic_store_store_api()
            .call_invoke(&mut store, &request)
            .await
            .map_err(ComponentError::Trap)?
            .map_err(ComponentError::Guest)?;

        Ok(ComponentInvocation {
            bindings,
            invocation: Some(invocation),
            store,
        })
    }
}

/// An isolated active invocation and its owning Wasmtime execution store.
pub struct ComponentInvocation {
    bindings: SemanticStore,
    invocation: Option<ResourceAny>,
    store: wasmtime::Store<HostState>,
}

impl std::fmt::Debug for ComponentInvocation {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("ComponentInvocation")
            .field("active", &self.invocation.is_some())
            .finish_non_exhaustive()
    }
}

impl ComponentInvocation {
    pub async fn next(&mut self) -> Result<Option<Vec<u8>>, ComponentError> {
        let invocation = self
            .invocation
            .ok_or_else(|| ComponentError::Guest("invocation is already complete".to_owned()))?;
        let event = self
            .bindings
            .reframe_semantic_store_store_api()
            .invocation()
            .call_next(&mut self.store, invocation)
            .await
            .map_err(ComponentError::Trap)?
            .map_err(ComponentError::Guest)?;

        if event.is_none() {
            self.drop_resource().await?;
        }
        Ok(event)
    }

    pub async fn finish(mut self) -> Result<(), ComponentError> {
        self.drop_resource().await
    }

    async fn drop_resource(&mut self) -> Result<(), ComponentError> {
        if let Some(invocation) = self.invocation.take() {
            invocation
                .resource_drop_async(&mut self.store)
                .await
                .map_err(ComponentError::Trap)?;
        }
        Ok(())
    }
}
