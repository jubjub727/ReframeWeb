use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};

use super::Operation;

#[derive(Debug, Serialize)]
pub struct Request {
    pub request_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub idempotency_key: Option<String>,
    #[serde(flatten)]
    pub operation: Operation,
}

#[derive(Deserialize)]
struct RequestParts {
    request_id: String,
    #[serde(default)]
    idempotency_key: Option<String>,
    #[serde(flatten)]
    operation: Map<String, Value>,
}

impl<'de> Deserialize<'de> for Request {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let parts = RequestParts::deserialize(deserializer)?;
        let operation = Operation::deserialize(Value::Object(parts.operation))
            .map_err(serde::de::Error::custom)?;
        Ok(Self {
            request_id: parts.request_id,
            idempotency_key: parts.idempotency_key,
            operation,
        })
    }
}
