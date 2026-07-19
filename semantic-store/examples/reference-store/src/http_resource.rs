use crate::{
    error::ResourceError,
    http_target::{HttpTarget, LoopbackTarget},
    model::{HttpSnapshot, HttpSnapshotSelector, LoopbackSelector, LoopbackSnapshot},
};

/// Injectable HTTP boundary; the component implementation uses WASI HTTP.
pub trait HttpClient {
    fn get(&self, target: &HttpTarget) -> Result<HttpSnapshot, ResourceError>;
}

pub(crate) fn read(
    selector: &HttpSnapshotSelector,
    http: &dyn HttpClient,
) -> Result<HttpSnapshot, ResourceError> {
    http.get(&HttpTarget::parse(&selector.url, selector.max_body_bytes)?)
}

pub(crate) fn read_loopback(
    selector: &LoopbackSelector,
    http: &dyn HttpClient,
) -> Result<LoopbackSnapshot, ResourceError> {
    let target = LoopbackTarget::parse(selector)?;
    let snapshot = http.get(target.http_target())?;
    Ok(LoopbackSnapshot {
        url: snapshot.url,
        status_code: snapshot.status_code,
        content_type: snapshot.content_type,
        body: snapshot.body,
    })
}

pub(crate) struct UnavailableHttp;

impl HttpClient for UnavailableHttp {
    fn get(&self, _target: &HttpTarget) -> Result<HttpSnapshot, ResourceError> {
        Err(ResourceError::Unavailable(
            "WASI HTTP is available only in the WebAssembly component".to_owned(),
        ))
    }
}
