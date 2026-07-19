use reframe_store_sdk::{
    DecodedInvocation, EventBuilder, GuestError, Invocation, InvocationOperation, PullInvocation,
};

use crate::{
    counter_resource::CounterSeries,
    error::ResourceError,
    http_resource::{self, HttpClient, UnavailableHttp},
    invocation_source::{CounterSubscription, DeferredUnary, DiagnosticTrap},
    model::{
        CounterSelector, DiagnosticTrapInput, HttpSnapshotSelector, LoopbackSelector,
        NormalizeLabelInput,
    },
    normalize_label,
};

const HTTP_RESOURCE: &str = "reference.http.loopback_snapshot";
const PUBLIC_HTTP_RESOURCE: &str = "reference.http.snapshot";
const COUNTER_RESOURCE: &str = "reference.streams.counter";
const DIAGNOSTIC_TRAP_FUNCTION: &str = "reference.diagnostics.trap";

/// Creates one fixed-boundary invocation without exposing protocol plumbing.
pub fn invoke(request_bytes: &[u8]) -> Result<Invocation, GuestError> {
    invoke_with_http(request_bytes, UnavailableHttp)
}

/// Creates an invocation with an owned HTTP implementation retained until pull.
pub fn invoke_with_http(
    request_bytes: &[u8],
    http: impl HttpClient + 'static,
) -> Result<Invocation, GuestError> {
    let request = DecodedInvocation::decode(request_bytes)?;

    match (request.operation(), request.operation().capability_id()) {
        (InvocationOperation::ReadResource(_), HTTP_RESOURCE) => read_http(&request, http),
        (InvocationOperation::ReadResource(_), PUBLIC_HTTP_RESOURCE) => {
            read_public_http(&request, http)
        }
        (InvocationOperation::ReadResource(_), COUNTER_RESOURCE) => read_counter(&request),
        (InvocationOperation::SubscribeResource(_), COUNTER_RESOURCE) => {
            subscribe_counter(&request)
        }
        (InvocationOperation::CallFunction(_), normalize_label::FUNCTION_ID) => {
            call_normalize_label(&request)
        }
        (InvocationOperation::CallFunction(_), DIAGNOSTIC_TRAP_FUNCTION) => {
            run_diagnostic_trap(&request)
        }
        _ => fail(
            &request,
            ResourceError::InvalidInput(format!(
                "unsupported operation for capability {:?}",
                request.operation().capability_id()
            )),
        ),
    }
}

fn call_normalize_label(request: &DecodedInvocation) -> Result<Invocation, GuestError> {
    let input = match request.input::<NormalizeLabelInput>() {
        Ok(input) => input,
        Err(error) => return fail(request, ResourceError::InvalidInput(error.to_string())),
    };
    pull(
        request,
        DeferredUnary::new(move || normalize_label::normalize(&input)),
    )
}

fn read_http(
    request: &DecodedInvocation,
    http: impl HttpClient + 'static,
) -> Result<Invocation, GuestError> {
    let selector = match request.input::<LoopbackSelector>() {
        Ok(selector) => selector,
        Err(error) => return fail(request, ResourceError::InvalidInput(error.to_string())),
    };
    pull(
        request,
        DeferredUnary::new(move || http_resource::read_loopback(&selector, &http)),
    )
}

fn read_public_http(
    request: &DecodedInvocation,
    http: impl HttpClient + 'static,
) -> Result<Invocation, GuestError> {
    let selector = match request.input::<HttpSnapshotSelector>() {
        Ok(selector) => selector,
        Err(error) => return fail(request, ResourceError::InvalidInput(error.to_string())),
    };
    pull(
        request,
        DeferredUnary::new(move || http_resource::read(&selector, &http)),
    )
}

fn read_counter(request: &DecodedInvocation) -> Result<Invocation, GuestError> {
    let selector = match request.input::<CounterSelector>() {
        Ok(selector) => selector,
        Err(error) => return fail(request, ResourceError::InvalidInput(error.to_string())),
    };
    let mut series = match CounterSeries::new(&selector) {
        Ok(series) => series,
        Err(error) => return fail(request, error),
    };
    pull(
        request,
        DeferredUnary::new(move || {
            Ok(series
                .next_sample()
                .expect("validated counter has one sample"))
        }),
    )
}

fn subscribe_counter(request: &DecodedInvocation) -> Result<Invocation, GuestError> {
    let selector = match request.input::<CounterSelector>() {
        Ok(selector) => selector,
        Err(error) => return fail(request, ResourceError::InvalidInput(error.to_string())),
    };
    let series = match CounterSeries::new(&selector) {
        Ok(series) => series,
        Err(error) => return fail(request, error),
    };
    pull(request, CounterSubscription::new(series))
}

fn run_diagnostic_trap(request: &DecodedInvocation) -> Result<Invocation, GuestError> {
    if let Err(error) = request.input::<DiagnosticTrapInput>() {
        return fail(request, ResourceError::InvalidInput(error.to_string()));
    }
    pull(request, DiagnosticTrap)
}

fn pull(
    request: &DecodedInvocation,
    source: impl reframe_store_sdk::InvocationSource + 'static,
) -> Result<Invocation, GuestError> {
    PullInvocation::for_request(request, source)
        .map(Invocation::from)
        .map_err(GuestError::from)
}

fn fail(request: &DecodedInvocation, error: ResourceError) -> Result<Invocation, GuestError> {
    EventBuilder::for_request(request)?
        .failure(
            error.failure_code(),
            error.to_string(),
            error.retryable(),
            None,
        )
        .map(Invocation::from)
        .map_err(GuestError::from)
}
