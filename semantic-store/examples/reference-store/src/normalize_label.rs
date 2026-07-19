use crate::{
    error::ResourceError,
    model::{NormalizeLabelInput, NormalizeLabelOutput},
};

pub const FUNCTION_ID: &str = "reference.text.normalize_label";

const MAX_LABEL_BYTES: usize = 256;

/// Produces a stable label by trimming and collapsing Unicode whitespace.
pub(crate) fn normalize(
    input: &NormalizeLabelInput,
) -> Result<NormalizeLabelOutput, ResourceError> {
    if input.label.len() > MAX_LABEL_BYTES {
        return Err(ResourceError::InvalidInput(format!(
            "label exceeds {MAX_LABEL_BYTES} UTF-8 bytes"
        )));
    }

    let mut words = input.label.split_whitespace();
    let first = words
        .next()
        .ok_or_else(|| ResourceError::InvalidInput("label must not be blank".to_owned()))?;
    let mut normalized_label = String::with_capacity(input.label.len());
    normalized_label.push_str(first);
    for word in words {
        normalized_label.push(' ');
        normalized_label.push_str(word);
    }

    Ok(NormalizeLabelOutput { normalized_label })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trims_and_collapses_whitespace_without_changing_case() {
        let output = normalize(&NormalizeLabelInput {
            label: "  Semantic\tStore\nLabel  ".to_owned(),
        })
        .expect("valid label");

        assert_eq!(output.normalized_label, "Semantic Store Label");
    }

    #[test]
    fn rejects_blank_labels() {
        let error = normalize(&NormalizeLabelInput {
            label: " \t\n".to_owned(),
        })
        .expect_err("blank label");

        assert!(matches!(error, ResourceError::InvalidInput(_)));
    }
}
