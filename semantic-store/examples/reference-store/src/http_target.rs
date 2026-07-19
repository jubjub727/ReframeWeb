use url::{Host, Url};

use crate::{error::ResourceError, model::LoopbackSelector};

const DEFAULT_MAX_BODY_BYTES: usize = 256 * 1024;
const HARD_MAX_BODY_BYTES: usize = 1024 * 1024;
const MAX_URL_BYTES: usize = 4 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HttpScheme {
    Http,
    Https,
}

/// A validated, bounded HTTP or HTTPS request target.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HttpTarget {
    authority: String,
    max_body_bytes: usize,
    path_and_query: String,
    scheme: HttpScheme,
    url: String,
}

impl HttpTarget {
    pub(crate) fn parse(url: &str, max_body_bytes: u32) -> Result<Self, ResourceError> {
        if url.len() > MAX_URL_BYTES {
            return Err(ResourceError::InvalidInput(format!(
                "URL must not exceed {MAX_URL_BYTES} UTF-8 bytes"
            )));
        }
        let parsed = validate_url(url)?;
        let scheme = match parsed.scheme() {
            "http" => HttpScheme::Http,
            "https" => HttpScheme::Https,
            _ => unreachable!("URL scheme was validated"),
        };
        let host = parsed.host_str().expect("URL host was validated");
        let host = if matches!(parsed.host(), Some(Host::Ipv6(_))) {
            format!("[{host}]")
        } else {
            host.to_owned()
        };
        let authority = parsed
            .port()
            .map_or_else(|| host.clone(), |port| format!("{host}:{port}"));
        let mut path_and_query = parsed.path().to_owned();
        if let Some(query) = parsed.query() {
            path_and_query.push('?');
            path_and_query.push_str(query);
        }
        let requested_limit = max_body_bytes as usize;
        if requested_limit > HARD_MAX_BODY_BYTES {
            return Err(ResourceError::InvalidInput(format!(
                "max_body_bytes must not exceed {HARD_MAX_BODY_BYTES}"
            )));
        }
        Ok(Self {
            authority,
            max_body_bytes: if requested_limit == 0 {
                DEFAULT_MAX_BODY_BYTES
            } else {
                requested_limit
            },
            path_and_query,
            scheme,
            url: url.to_owned(),
        })
    }

    #[must_use]
    pub fn authority(&self) -> &str {
        &self.authority
    }

    #[must_use]
    pub const fn max_body_bytes(&self) -> usize {
        self.max_body_bytes
    }

    #[must_use]
    pub fn path_and_query(&self) -> &str {
        &self.path_and_query
    }

    #[must_use]
    pub const fn scheme(&self) -> HttpScheme {
        self.scheme
    }

    #[must_use]
    pub fn url(&self) -> &str {
        &self.url
    }
}

/// A general target additionally proven to address localhost or a loopback IP.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoopbackTarget(HttpTarget);

impl LoopbackTarget {
    pub(crate) fn parse(selector: &LoopbackSelector) -> Result<Self, ResourceError> {
        let target = HttpTarget::parse(&selector.url, selector.max_body_bytes)?;
        let url = Url::parse(target.url()).expect("HTTP target URL was validated");
        let is_loopback = match url.host() {
            Some(Host::Domain(domain)) => domain.eq_ignore_ascii_case("localhost"),
            Some(Host::Ipv4(address)) => address.is_loopback(),
            Some(Host::Ipv6(address)) => address.is_loopback(),
            None => false,
        };
        if !is_loopback {
            return Err(ResourceError::InvalidInput(
                "reference loopback resource accepts only localhost or loopback IP URLs".to_owned(),
            ));
        }
        Ok(Self(target))
    }

    pub(crate) const fn http_target(&self) -> &HttpTarget {
        &self.0
    }

    #[must_use]
    pub fn authority(&self) -> &str {
        self.0.authority()
    }

    #[must_use]
    pub const fn max_body_bytes(&self) -> usize {
        self.0.max_body_bytes()
    }

    #[must_use]
    pub fn path_and_query(&self) -> &str {
        self.0.path_and_query()
    }

    #[must_use]
    pub const fn scheme(&self) -> HttpScheme {
        self.0.scheme()
    }

    #[must_use]
    pub fn url(&self) -> &str {
        self.0.url()
    }
}

fn validate_url(value: &str) -> Result<Url, ResourceError> {
    let url = Url::parse(value)
        .map_err(|error| ResourceError::InvalidInput(format!("invalid URL: {error}")))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(ResourceError::InvalidInput(
            "URL scheme must be http or https".to_owned(),
        ));
    }
    if url.host().is_none() {
        return Err(ResourceError::InvalidInput(
            "URL must contain a host".to_owned(),
        ));
    }
    if !url.username().is_empty() || url.password().is_some() || url.fragment().is_some() {
        return Err(ResourceError::InvalidInput(
            "URL must not contain credentials or a fragment".to_owned(),
        ));
    }
    Ok(url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_general_https_and_bounded_loopback_targets() {
        let https = HttpTarget::parse("https://example.com/data?q=1", 4096).unwrap();
        assert_eq!(https.scheme(), HttpScheme::Https);
        assert_eq!(https.authority(), "example.com");
        assert_eq!(https.path_and_query(), "/data?q=1");

        let loopback = LoopbackTarget::parse(&LoopbackSelector {
            url: "http://127.0.0.1:8080/data".to_owned(),
            max_body_bytes: 4096,
        })
        .unwrap();
        assert_eq!(loopback.authority(), "127.0.0.1:8080");
    }

    #[test]
    fn rejects_non_loopback_and_oversized_requests() {
        let remote = LoopbackSelector {
            url: "https://example.com".to_owned(),
            max_body_bytes: 4096,
        };
        assert!(LoopbackTarget::parse(&remote).is_err());
        assert!(
            HttpTarget::parse("http://localhost/data", HARD_MAX_BODY_BYTES as u32 + 1).is_err()
        );
        let oversized_url = format!("https://example.com/{}", "x".repeat(MAX_URL_BYTES));
        assert!(HttpTarget::parse(&oversized_url, 1024).is_err());
    }
}
