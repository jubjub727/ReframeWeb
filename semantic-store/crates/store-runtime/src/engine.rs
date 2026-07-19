use std::{sync::Arc, time::Duration};

use thiserror::Error;
use tokio::{task::JoinHandle, time};
use tokio_util::sync::CancellationToken;
use wasmtime::{Config, Engine, OptLevel};
use wasmtime_wasi_http::p2::add_to_linker_async;

use crate::host_state::HostState;

const DEFAULT_EPOCH_INTERVAL: Duration = Duration::from_millis(10);

/// Runtime compiler and cooperative-cancellation settings.
#[derive(Debug, Clone)]
pub struct EngineConfig {
    /// How often CPU-bound guest execution yields to Tokio.
    pub epoch_interval: Duration,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            epoch_interval: DEFAULT_EPOCH_INTERVAL,
        }
    }
}

/// Shared Wasmtime engine and linker used to compile Store components once.
///
/// Component instances and Wasmtime stores are deliberately not held here;
/// each invocation owns those independently.
pub struct RuntimeEngine {
    engine: Engine,
    linker: Arc<wasmtime::component::Linker<HostState>>,
    ticker: EpochTicker,
}

impl std::fmt::Debug for RuntimeEngine {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("RuntimeEngine")
            .finish_non_exhaustive()
    }
}

impl RuntimeEngine {
    pub fn new(settings: EngineConfig) -> Result<Self, EngineError> {
        if settings.epoch_interval.is_zero() {
            return Err(EngineError::ZeroEpochInterval);
        }

        let mut config = Config::new();
        config
            .epoch_interruption(true)
            .wasm_component_model(true)
            .cranelift_opt_level(OptLevel::Speed);
        let engine = Engine::new(&config).map_err(EngineError::Wasmtime)?;
        let mut linker = wasmtime::component::Linker::new(&engine);
        add_to_linker_async(&mut linker).map_err(EngineError::Wasmtime)?;
        let ticker = EpochTicker::start(engine.clone(), settings.epoch_interval)?;

        Ok(Self {
            engine,
            linker: Arc::new(linker),
            ticker,
        })
    }

    pub(crate) fn engine(&self) -> &Engine {
        &self.engine
    }

    pub(crate) fn linker(&self) -> &wasmtime::component::Linker<HostState> {
        &self.linker
    }

    pub(crate) fn new_store(&self) -> wasmtime::Store<HostState> {
        let mut store = wasmtime::Store::new(&self.engine, HostState::new());
        store.epoch_deadline_async_yield_and_update(1);
        store
    }
}

impl Drop for RuntimeEngine {
    fn drop(&mut self) {
        self.ticker.stop();
    }
}

struct EpochTicker {
    cancel: CancellationToken,
    task: Option<JoinHandle<()>>,
}

impl EpochTicker {
    fn start(engine: Engine, interval: Duration) -> Result<Self, EngineError> {
        let handle = tokio::runtime::Handle::try_current().map_err(EngineError::TokioRuntime)?;
        let cancel = CancellationToken::new();
        let task_cancel = cancel.clone();
        let task = handle.spawn(async move {
            let mut ticks = time::interval(interval);
            ticks.set_missed_tick_behavior(time::MissedTickBehavior::Skip);
            loop {
                tokio::select! {
                    _ = task_cancel.cancelled() => break,
                    _ = ticks.tick() => engine.increment_epoch(),
                }
            }
        });
        Ok(Self {
            cancel,
            task: Some(task),
        })
    }

    fn stop(&mut self) {
        self.cancel.cancel();
        if let Some(task) = self.task.take() {
            task.abort();
        }
    }
}

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum EngineError {
    #[error("Wasmtime epoch interval must be greater than zero")]
    ZeroEpochInterval,
    #[error("RuntimeEngine must be created inside a Tokio runtime")]
    TokioRuntime(#[source] tokio::runtime::TryCurrentError),
    #[error("could not configure the Wasmtime engine: {0}")]
    Wasmtime(wasmtime::Error),
}

impl std::fmt::Debug for EpochTicker {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("EpochTicker")
            .finish_non_exhaustive()
    }
}
