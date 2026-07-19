use std::collections::BTreeSet;

use unicode_normalization::UnicodeNormalization;

/// Applies Unicode compatibility normalization and lowercase expansion, then
/// splits on Unicode non-alphanumeric characters. A second NFKC pass makes
/// lowercase expansions canonical as well.
pub(crate) fn terms(value: &str) -> Vec<String> {
    let mut output = Vec::new();
    let mut token = String::new();
    let lowercase = value
        .nfkc()
        .flat_map(char::to_lowercase)
        .collect::<String>();
    for character in lowercase.nfkc() {
        if character.is_alphanumeric() {
            token.extend(character.to_lowercase());
        } else if !token.is_empty() {
            output.push(std::mem::take(&mut token));
        }
    }
    if !token.is_empty() {
        output.push(token);
    }
    output
}

pub(crate) fn unique_terms(value: &str) -> Vec<String> {
    terms(value)
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalization_is_unicode_aware_and_deterministic() {
        assert_eq!(
            terms("  CAFÉ—東京 Cafe\u{301} ①  "),
            ["café", "東京", "café", "1"]
        );
        assert_eq!(unique_terms("Zulu zulu ALPHA"), ["alpha", "zulu"]);
    }
}
