use reframe_store_protocol::wire::{
    GetSchemaBundleRequest, GetSchemaBundleResponse, get_schema_bundle_response,
};

use crate::{CatalogError, CatalogService};

impl CatalogService {
    /// Returns the exact packaged descriptor bytes, or an unchanged marker when
    /// the caller already has the exact artifact hash.
    pub fn get_schema_bundle(
        &self,
        request: &GetSchemaBundleRequest,
    ) -> Result<GetSchemaBundleResponse, CatalogError> {
        let result = if request.known_artifact_hash == self.schema_hash {
            get_schema_bundle_response::Result::Unchanged(true)
        } else {
            get_schema_bundle_response::Result::DescriptorSet(self.schema_bundle.to_vec())
        };
        Ok(GetSchemaBundleResponse {
            artifact_hash: self.schema_hash.to_vec(),
            result: Some(result),
        })
    }
}
