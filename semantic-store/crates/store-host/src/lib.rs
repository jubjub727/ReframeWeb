//! Thin composition layer for the Semantic Store runtime and local transport.

mod frame_policy;
mod transport_adapter;

use std::{collections::HashSet, io, sync::Arc};

use reframe_store_package::VerifiedPackage;
use reframe_store_runtime::{
    EngineConfig, EngineError, RegisterError, RuntimeConfig, RuntimeEngine, SemanticStoreRuntime,
    StoreRegistry,
};
use reframe_store_transport::{
    LocalEndpoint, LocalListener, ServerError, TransportConfig, serve_local,
};
use thiserror::Error;
use tokio_util::sync::CancellationToken;

pub use crate::frame_policy::FrameCompatibilityError;
use crate::{frame_policy::FramePolicy, transport_adapter::RuntimeHandler};

/// A verified package set composed with one reusable runtime.
#[derive(Debug)]
pub struct StoreHost {
    frame_policy: FramePolicy,
    registry: Arc<StoreRegistry>,
    runtime: Arc<SemanticStoreRuntime>,
    transport_config: TransportConfig,
}

impl StoreHost {
    pub async fn new(
        packages: impl IntoIterator<Item = VerifiedPackage>,
        engine_config: EngineConfig,
        runtime_config: RuntimeConfig,
    ) -> Result<Self, HostBuildError> {
        Self::new_with_transport(
            packages,
            engine_config,
            runtime_config,
            TransportConfig::default(),
        )
        .await
    }

    /// Builds a host whose frame limit cannot change underneath package or
    /// response compatibility checks.
    pub async fn new_with_transport(
        packages: impl IntoIterator<Item = VerifiedPackage>,
        engine_config: EngineConfig,
        runtime_config: RuntimeConfig,
        transport_config: TransportConfig,
    ) -> Result<Self, HostBuildError> {
        let frame_policy = FramePolicy::new(&runtime_config, transport_config.max_frame_size())?;
        let packages = packages.into_iter().collect::<Vec<_>>();
        if packages.is_empty() {
            return Err(HostBuildError::NoPackages);
        }
        let mut store_ids = HashSet::with_capacity(packages.len());
        for package in &packages {
            let store_id = package.manifest().store_id.clone();
            if !store_ids.insert(store_id.clone()) {
                return Err(HostBuildError::DuplicateStoreId { store_id });
            }
            frame_policy.validate_package(package)?;
        }

        let engine = Arc::new(RuntimeEngine::new(engine_config)?);
        let registry = Arc::new(StoreRegistry::new(engine));
        for package in packages {
            registry.register(package).await?;
        }
        let runtime = Arc::new(SemanticStoreRuntime::new(
            Arc::clone(&registry),
            runtime_config,
        ));
        Ok(Self {
            frame_policy,
            registry,
            runtime,
            transport_config,
        })
    }

    /// Registers a revision only after proving its unbudgeted responses fit the
    /// immutable transport frame limit. Existing sessions retain their prior revision.
    pub async fn register(&self, package: VerifiedPackage) -> Result<(), HostRegistrationError> {
        self.frame_policy.validate_package(&package)?;
        self.registry.register(package).await?;
        Ok(())
    }

    /// Serves until shutdown or a listener-level failure, then cancels every
    /// guest invocation before allowing transport writers to drain.
    pub async fn serve(
        &self,
        endpoint: &LocalEndpoint,
        shutdown: CancellationToken,
    ) -> Result<(), HostServeError> {
        let listener = LocalListener::bind(endpoint).map_err(HostServeError::Bind)?;
        let handler = Arc::new(RuntimeHandler::new(
            Arc::clone(&self.runtime),
            self.frame_policy.clone(),
        ));
        tracing::info!(endpoint = %endpoint, stores = self.registry.list().len(), "Semantic Store host listening");

        let server = serve_local(
            listener,
            handler,
            self.transport_config.clone(),
            shutdown.clone(),
        );
        tokio::pin!(server);
        let result = tokio::select! {
            result = &mut server => result,
            () = shutdown.cancelled() => {
                self.runtime.shutdown().await;
                server.await
            }
        };
        self.runtime.shutdown().await;
        result.map_err(HostServeError::Server)
    }
}

#[derive(Debug, Error)]
pub enum HostBuildError {
    #[error("at least one verified Store package is required")]
    NoPackages,
    #[error("Store ID {store_id} was supplied more than once")]
    DuplicateStoreId { store_id: String },
    #[error(transparent)]
    Engine(#[from] EngineError),
    #[error(transparent)]
    Frame(#[from] FrameCompatibilityError),
    #[error("Store package could not be registered")]
    Register(#[from] RegisterError),
}

#[derive(Debug, Error)]
pub enum HostRegistrationError {
    #[error(transparent)]
    Frame(#[from] FrameCompatibilityError),
    #[error("Store package could not be registered")]
    Register(#[from] RegisterError),
}

#[derive(Debug, Error)]
pub enum HostServeError {
    #[error("could not bind the local Semantic Store endpoint")]
    Bind(#[source] io::Error),
    #[error("local Semantic Store server failed")]
    Server(#[source] ServerError),
}
