include!("transport.rs");

struct Daemon {
    store: Store,
    residents: HashMap<String, Arc<ResidentWorkspace>>,
    #[cfg(any(windows, unix))]
    mounts: HashMap<String, Provider>,
    #[cfg(not(any(windows, unix)))]
    mounts: HashMap<String, ()>,
}

impl Daemon {
    fn open(root: &Path) -> Result<Self> {
        Ok(Self {
            store: Store::open(root)?,
            residents: HashMap::new(),
            mounts: HashMap::new(),
        })
    }

    fn handle(&mut self, request: Request) -> Response {
        let operation_name = request.operation.name();
        if request.operation.mutates() {
            if let Some(key) = request.idempotency_key.as_deref() {
                match self.cached_response(key, operation_name) {
                    Ok(Some(mut response)) => {
                        response.request_id.clone_from(&request.request_id);
                        return response;
                    }
                    Ok(None) => {}
                    Err(error) => {
                        return failure(&request, "idempotency_error", &error.to_string());
                    }
                }
            } else {
                return failure(
                    &request,
                    "idempotency_required",
                    "mutating operations require idempotency_key",
                );
            }
        }
        let result = self.execute(&request.operation);
        let response = match result {
            Ok(value) => Response {
                request_id: request.request_id.clone(),
                ok: true,
                result: Some(value),
                error: None,
            },
            Err(error) => failure(&request, "operation_failed", &format!("{error:#}")),
        };
        if request.operation.mutates() {
            if let Some(key) = request.idempotency_key.as_deref() {
                if let Err(error) = self.cache_response(key, operation_name, &response) {
                    eprintln!(
                        "[workspace-daemon] failed to persist idempotent response: {error:#}"
                    );
                }
            }
        }
        response
    }

}

include!("operations.rs");
include!("lifecycle.rs");
include!("idempotency.rs");
