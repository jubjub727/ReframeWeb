use reframe_store_sdk::{GuestError, InvocationSource, InvocationStep, StoreMessage};

use crate::{counter_resource::CounterSeries, error::ResourceError};

pub(crate) struct DeferredUnary {
    operation: Option<Box<dyn FnOnce() -> Result<InvocationStep, GuestError>>>,
}

impl DeferredUnary {
    pub(crate) fn new<T, F>(operation: F) -> Self
    where
        T: StoreMessage,
        F: FnOnce() -> Result<T, ResourceError> + 'static,
    {
        Self {
            operation: Some(Box::new(move || match operation() {
                Ok(value) => InvocationStep::data(&value),
                Err(error) => Ok(failure(&error)),
            })),
        }
    }
}

impl InvocationSource for DeferredUnary {
    fn next(&mut self) -> Result<InvocationStep, GuestError> {
        match self.operation.take() {
            Some(operation) => operation(),
            None => Ok(InvocationStep::Complete),
        }
    }
}

pub(crate) struct CounterSubscription {
    phase: CounterPhase,
    series: CounterSeries,
}

pub(crate) struct DiagnosticTrap;

impl InvocationSource for DiagnosticTrap {
    fn next(&mut self) -> Result<InvocationStep, GuestError> {
        panic!("intentional reference Store diagnostic trap")
    }
}

impl CounterSubscription {
    pub(crate) const fn new(series: CounterSeries) -> Self {
        Self {
            phase: CounterPhase::Sample,
            series,
        }
    }
}

impl InvocationSource for CounterSubscription {
    fn next(&mut self) -> Result<InvocationStep, GuestError> {
        match self.phase {
            CounterPhase::Sample => {
                let sample = self
                    .series
                    .next_sample()
                    .expect("counter phase guarantees a remaining sample");
                self.phase = CounterPhase::Progress;
                InvocationStep::data(&sample)
            }
            CounterPhase::Progress => {
                let completed = self.series.produced();
                self.phase = if completed == self.series.total() {
                    CounterPhase::Complete
                } else {
                    CounterPhase::Sample
                };
                Ok(InvocationStep::progress(
                    u64::from(completed),
                    Some(u64::from(self.series.total())),
                    "samples",
                    "Produced counter sample",
                ))
            }
            CounterPhase::Complete => Ok(InvocationStep::Complete),
        }
    }
}

#[derive(Clone, Copy)]
enum CounterPhase {
    Sample,
    Progress,
    Complete,
}

pub(crate) fn failure(error: &ResourceError) -> InvocationStep {
    InvocationStep::failure(
        error.failure_code(),
        error.to_string(),
        error.retryable(),
        None,
    )
}
