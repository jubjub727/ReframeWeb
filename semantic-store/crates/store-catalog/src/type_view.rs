use prost::Message;
use reframe_store_protocol::wire::{InspectTypeRequest, InspectTypeResponse, TypeView};

use crate::{
    CatalogError, CatalogService, MAX_SCHEMA_DEPTH,
    budget::{ProjectionBudget, inspection_budget},
    field_selection::{Selection, build_selection},
    type_projection::{project_enum, project_message},
};

impl CatalogService {
    /// Projects a protobuf message or enum without exposing the descriptor set.
    /// Explicit budgets above [`crate::MAX_INSPECTION_BYTE_BUDGET`] are rejected.
    pub fn inspect_type(
        &self,
        request: &InspectTypeRequest,
    ) -> Result<InspectTypeResponse, CatalogError> {
        let type_name = canonical_type_name(&request.type_name);
        let depth = normalized_depth(request.depth);
        let response_budget = inspection_budget(request.byte_budget)?;
        let selection = if request.field_paths.is_empty() {
            Selection::All
        } else {
            let message = self
                .descriptor_pool
                .get_message_by_name(type_name)
                .ok_or_else(|| CatalogError::TypeNotFound {
                    type_name: request.type_name.clone(),
                })?;
            build_selection(&message, &request.field_paths, &request.type_name)?
        };
        let mut projection_budget = ProjectionBudget::new(response_budget);
        let view = self.project_named_type(type_name, &selection, depth, &mut projection_budget)?;
        let mut response = InspectTypeResponse { r#type: Some(view) };
        fit_type_response(&mut response, response_budget)?;
        Ok(response)
    }

    pub(crate) fn project_complete_type(
        &self,
        type_name: &str,
        depth: usize,
        budget: &mut ProjectionBudget,
    ) -> Result<TypeView, CatalogError> {
        self.project_named_type(
            canonical_type_name(type_name),
            &Selection::All,
            depth.clamp(1, MAX_SCHEMA_DEPTH),
            budget,
        )
    }

    fn project_named_type(
        &self,
        type_name: &str,
        selection: &Selection,
        depth: usize,
        budget: &mut ProjectionBudget,
    ) -> Result<TypeView, CatalogError> {
        if let Some(message) = self.descriptor_pool.get_message_by_name(type_name) {
            return Ok(project_message(&message, selection, depth, budget));
        }
        if let Some(enumeration) = self.descriptor_pool.get_enum_by_name(type_name) {
            return Ok(project_enum(&enumeration, budget));
        }
        Err(CatalogError::TypeNotFound {
            type_name: type_name.to_owned(),
        })
    }
}

pub(crate) fn normalized_depth(value: u32) -> usize {
    if value == 0 {
        1
    } else {
        usize::try_from(value)
            .unwrap_or(MAX_SCHEMA_DEPTH)
            .min(MAX_SCHEMA_DEPTH)
    }
}

pub(crate) fn prune_type(view: &mut TypeView) -> bool {
    for field in view.fields.iter_mut().rev() {
        if let Some(nested) = field.nested.as_mut() {
            if prune_type(nested) {
                field.truncated = true;
                view.truncated = true;
                return true;
            }
            field.nested = None;
            field.truncated = true;
            view.truncated = true;
            return true;
        }
    }
    if view.fields.pop().is_some() || view.enum_values.pop().is_some() {
        view.truncated = true;
        return true;
    }
    false
}

fn fit_type_response(
    response: &mut InspectTypeResponse,
    budget: usize,
) -> Result<(), CatalogError> {
    while response.encoded_len() > budget {
        let Some(view) = response.r#type.as_mut() else {
            break;
        };
        if !prune_type(view) {
            return Err(CatalogError::BudgetExceeded {
                budget,
                required: response.encoded_len(),
            });
        }
    }
    Ok(())
}

fn canonical_type_name(type_name: &str) -> &str {
    type_name.trim().trim_start_matches('.')
}
