use std::collections::BTreeSet;

use prost::Message;
use reframe_store_protocol::{
    package::catalog_entry,
    wire::{
        ErrorView, ExampleView, InspectCapabilityRequest, InspectCapabilityResponse,
        InspectionSection, SideEffectView, WorkflowStepView,
    },
};

use crate::{
    CatalogError, CatalogService, DEFAULT_EXAMPLE_LIMIT,
    budget::{ProjectionBudget, inspection_budget},
    discovery::catalog_hit,
    service::entry_kind,
    type_view::{normalized_depth, prune_type},
};

impl CatalogService {
    /// Returns exactly the requested capability sections, subject to complete
    /// item, example-count, schema-depth, and encoded-response budgets. Explicit
    /// budgets above [`crate::MAX_INSPECTION_BYTE_BUDGET`] are rejected.
    pub fn inspect_capability(
        &self,
        request: &InspectCapabilityRequest,
    ) -> Result<InspectCapabilityResponse, CatalogError> {
        let entry = self.entry(&request.capability_id)?;
        let sections = normalized_sections(&request.sections)?;
        let mut response = InspectCapabilityResponse {
            capability_id: entry.id.clone(),
            kind: entry_kind(entry)? as i32,
            ..Default::default()
        };
        let guidance = entry.guidance.as_ref();
        let response_budget = inspection_budget(request.byte_budget)?;

        if sections.contains(&InspectionSection::Summary) {
            response.summary = Some(entry.summary.clone());
        }
        if sections.contains(&InspectionSection::WhenToUse) {
            response.when_to_use = guidance.map(|value| value.when_to_use.clone());
        }
        if sections.contains(&InspectionSection::WhenNotToUse) {
            response.when_not_to_use = guidance.map(|value| value.when_not_to_use.clone());
        }

        let depth = normalized_depth(request.schema_depth);
        let mut input_type = None;
        let mut output_type = None;
        match entry.kind.as_ref() {
            Some(catalog_entry::Kind::Resource(resource)) => {
                if sections.contains(&InspectionSection::Input) {
                    input_type = Some(resource.selector_type.as_str());
                }
                if sections.contains(&InspectionSection::Output) {
                    output_type = Some(resource.value_type.as_str());
                }
            }
            Some(catalog_entry::Kind::Function(function)) => {
                if sections.contains(&InspectionSection::Input) {
                    input_type = Some(function.input_type.as_str());
                }
                if sections.contains(&InspectionSection::Output) {
                    output_type = Some(function.output_type.as_str());
                }
                if sections.contains(&InspectionSection::SideEffects) {
                    response.side_effects = Some(SideEffectView {
                        classification: function.side_effect,
                        idempotency: function.idempotency,
                    });
                }
            }
            Some(catalog_entry::Kind::Workflow(workflow)) => {
                if sections.contains(&InspectionSection::WorkflowSteps) {
                    response.workflow_steps = workflow
                        .steps
                        .iter()
                        .map(|step| WorkflowStepView {
                            instruction: step.instruction.clone(),
                            capability_id: step.capability_id.clone(),
                            condition: step.condition.clone(),
                        })
                        .collect();
                }
            }
            Some(catalog_entry::Kind::Topic(_)) | None => {}
        }

        if sections.contains(&InspectionSection::Errors) {
            response.errors = guidance
                .into_iter()
                .flat_map(|value| &value.errors)
                .map(|error| ErrorView {
                    code: error.code.clone(),
                    summary: error.summary.clone(),
                    recovery: error.recovery.clone(),
                })
                .collect();
        }
        if sections.contains(&InspectionSection::Examples) {
            let example_limit = if request.example_limit == 0 {
                DEFAULT_EXAMPLE_LIMIT
            } else {
                usize::try_from(request.example_limit).unwrap_or(usize::MAX)
            };
            response.examples = guidance
                .into_iter()
                .flat_map(|value| &value.examples)
                .take(example_limit)
                .map(|example| ExampleView {
                    title: example.title.clone(),
                    description: example.description.clone(),
                    input: example.input.clone(),
                    output: example.output.clone(),
                })
                .collect();
        }
        if sections.contains(&InspectionSection::RelatedCapabilities) {
            response.related_capabilities = entry
                .related_entry_ids
                .iter()
                .map(|id| self.entry(id).and_then(catalog_hit))
                .collect::<Result<Vec<_>, _>>()?;
        }

        let available_projection_work = response_budget.saturating_sub(response.encoded_len());
        let mut projection_budget = ProjectionBudget::new(available_projection_work);
        // Exact response fitting prunes input before output, so construct output
        // first when both were requested and preserve the same priority under
        // the construction-work budget.
        if let Some(type_name) = output_type {
            response.output =
                Some(self.project_complete_type(type_name, depth, &mut projection_budget)?);
        }
        if let Some(type_name) = input_type {
            response.input =
                Some(self.project_complete_type(type_name, depth, &mut projection_budget)?);
        }

        fit_capability_response(&mut response, response_budget)?;
        Ok(response)
    }
}

fn normalized_sections(values: &[i32]) -> Result<BTreeSet<InspectionSection>, CatalogError> {
    let mut sections = BTreeSet::new();
    for value in values {
        let section = InspectionSection::try_from(*value)
            .map_err(|_| CatalogError::InvalidInspectionSection { value: *value })?;
        if section == InspectionSection::Unspecified {
            return Err(CatalogError::InvalidInspectionSection { value: *value });
        }
        sections.insert(section);
    }
    Ok(sections)
}

fn fit_capability_response(
    response: &mut InspectCapabilityResponse,
    budget: usize,
) -> Result<(), CatalogError> {
    while response.encoded_len() > budget {
        if response.input.as_mut().is_some_and(prune_type)
            || response.output.as_mut().is_some_and(prune_type)
            || response.workflow_steps.pop().is_some()
            || response.related_capabilities.pop().is_some()
            || response.examples.pop().is_some()
            || response.errors.pop().is_some()
        {
            continue;
        }
        return Err(CatalogError::BudgetExceeded {
            budget,
            required: response.encoded_len(),
        });
    }
    Ok(())
}
