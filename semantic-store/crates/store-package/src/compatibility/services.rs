use std::collections::BTreeMap;

use super::{index::SchemaIndex, violation::CompatibilityViolation};

pub(super) fn compare_services(
    previous: &SchemaIndex<'_>,
    candidate: &SchemaIndex<'_>,
    violations: &mut Vec<CompatibilityViolation>,
) {
    for (service_name, previous_service) in &previous.services {
        let Some(candidate_service) = candidate.services.get(service_name) else {
            violations.push(CompatibilityViolation::ServiceRemoved {
                service: service_name.clone(),
            });
            continue;
        };
        let candidate_methods = candidate_service
            .method
            .iter()
            .filter_map(|method| Some((method.name.as_deref()?, method)))
            .collect::<BTreeMap<_, _>>();
        let mut previous_methods = previous_service.method.iter().collect::<Vec<_>>();
        previous_methods.sort_unstable_by_key(|method| method.name.as_deref());
        for previous_method in previous_methods {
            let method_name = previous_method.name.as_deref().unwrap_or_default();
            let Some(candidate_method) = candidate_methods.get(method_name) else {
                violations.push(CompatibilityViolation::MethodRemoved {
                    service: service_name.clone(),
                    method: method_name.to_owned(),
                });
                continue;
            };
            compare_method(
                service_name,
                method_name,
                previous_method,
                candidate_method,
                violations,
            );
        }
    }
}

fn compare_method(
    service: &str,
    method: &str,
    previous: &prost_types::MethodDescriptorProto,
    candidate: &prost_types::MethodDescriptorProto,
    violations: &mut Vec<CompatibilityViolation>,
) {
    if previous.input_type != candidate.input_type {
        violations.push(CompatibilityViolation::RpcInputChanged {
            service: service.to_owned(),
            method: method.to_owned(),
            previous: previous.input_type.clone().unwrap_or_default(),
            candidate: candidate.input_type.clone().unwrap_or_default(),
        });
    }
    if previous.output_type != candidate.output_type {
        violations.push(CompatibilityViolation::RpcOutputChanged {
            service: service.to_owned(),
            method: method.to_owned(),
            previous: previous.output_type.clone().unwrap_or_default(),
            candidate: candidate.output_type.clone().unwrap_or_default(),
        });
    }
    let previous_client_streaming = previous.client_streaming.unwrap_or(false);
    let candidate_client_streaming = candidate.client_streaming.unwrap_or(false);
    if previous_client_streaming != candidate_client_streaming {
        violations.push(CompatibilityViolation::RpcClientStreamingChanged {
            service: service.to_owned(),
            method: method.to_owned(),
            previous: previous_client_streaming,
            candidate: candidate_client_streaming,
        });
    }
    let previous_server_streaming = previous.server_streaming.unwrap_or(false);
    let candidate_server_streaming = candidate.server_streaming.unwrap_or(false);
    if previous_server_streaming != candidate_server_streaming {
        violations.push(CompatibilityViolation::RpcServerStreamingChanged {
            service: service.to_owned(),
            method: method.to_owned(),
            previous: previous_server_streaming,
            candidate: candidate_server_streaming,
        });
    }
}
