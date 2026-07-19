#![forbid(unsafe_code)]

use reframe_reference_store::{HttpClient, HttpScheme, HttpSnapshot, HttpTarget, ResourceError};

use crate::bindings::wasi::{
    http::{
        outgoing_handler,
        types::{Fields, IncomingBody, Method, OutgoingRequest, Scheme},
    },
    io::streams::StreamError,
};

pub(crate) struct WasiHttp;

impl HttpClient for WasiHttp {
    fn get(&self, target: &HttpTarget) -> Result<HttpSnapshot, ResourceError> {
        let headers = Fields::new();
        let request = OutgoingRequest::new(headers);
        request
            .set_method(&Method::Get)
            .map_err(|()| unavailable("host rejected the HTTP method"))?;
        request
            .set_scheme(Some(&scheme(target.scheme())))
            .map_err(|()| unavailable("host rejected the URL scheme"))?;
        request
            .set_authority(Some(target.authority()))
            .map_err(|()| unavailable("host rejected the URL authority"))?;
        request
            .set_path_with_query(Some(target.path_and_query()))
            .map_err(|()| unavailable("host rejected the URL path"))?;

        let future = outgoing_handler::handle(request, None)
            .map_err(|_| unavailable("host could not start the HTTP request"))?;
        future.subscribe().block();
        let response = future
            .get()
            .ok_or_else(|| unavailable("HTTP response was not ready after polling"))?
            .map_err(|()| unavailable("HTTP response was already consumed"))?
            .map_err(|_| unavailable("HTTP request failed before receiving headers"))?;

        let status_code = u32::from(response.status());
        let content_type = response
            .headers()
            .get("content-type")
            .into_iter()
            .next()
            .and_then(|value| String::from_utf8(value).ok())
            .unwrap_or_default();
        let body = response
            .consume()
            .map_err(|()| unavailable("HTTP response body was already consumed"))?;
        let stream = body
            .stream()
            .map_err(|()| unavailable("HTTP response body stream was already taken"))?;
        let bytes = read_body(&stream, target.max_body_bytes())?;
        drop(stream);
        drop(IncomingBody::finish(body));

        Ok(HttpSnapshot {
            url: target.url().to_owned(),
            status_code,
            content_type,
            body: bytes,
        })
    }
}

fn read_body(
    stream: &crate::bindings::wasi::io::streams::InputStream,
    limit: usize,
) -> Result<Vec<u8>, ResourceError> {
    let mut bytes = Vec::new();
    loop {
        let remaining = limit.saturating_sub(bytes.len());
        if remaining == 0 {
            return match stream.blocking_read(1) {
                Ok(chunk) if chunk.is_empty() => Ok(bytes),
                Err(StreamError::Closed) => Ok(bytes),
                _ => Err(response_too_large(limit)),
            };
        }
        let read_size = remaining.min(16 * 1024) as u64;
        match stream.blocking_read(read_size) {
            Ok(chunk) if chunk.is_empty() => {
                return Err(unavailable("HTTP body stream returned an empty read"));
            }
            Ok(chunk) => bytes.extend_from_slice(&chunk),
            Err(StreamError::Closed) => return Ok(bytes),
            Err(StreamError::LastOperationFailed(_)) => {
                return Err(unavailable("HTTP response body stream failed"));
            }
        }
    }
}

const fn scheme(value: HttpScheme) -> Scheme {
    match value {
        HttpScheme::Http => Scheme::Http,
        HttpScheme::Https => Scheme::Https,
    }
}

fn unavailable(message: &str) -> ResourceError {
    ResourceError::Unavailable(message.to_owned())
}

fn response_too_large(limit: usize) -> ResourceError {
    ResourceError::ResponseTooLarge(format!(
        "HTTP response body exceeds the configured {limit}-byte limit"
    ))
}
