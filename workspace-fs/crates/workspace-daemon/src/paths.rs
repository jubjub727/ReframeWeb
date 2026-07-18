use std::path::{Component, Path, PathBuf};

use anyhow::{Result, bail};
use globset::{GlobBuilder, GlobSet, GlobSetBuilder};

pub const SCRATCH_SEGMENTS: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".reframe-memory",
    ".reframe-workspace",
    ".ruff_cache",
    ".tox",
    ".venv",
    "node_modules",
    "target",
    ".next",
    "dist",
    "build",
    ".cache",
    "__pycache__",
];

pub fn normalize_relative(value: &Path) -> Result<String> {
    if value.as_os_str().is_empty() || value.is_absolute() {
        bail!(
            "workspace path must be a non-empty relative path: {}",
            value.display()
        );
    }
    let mut parts = Vec::new();
    for component in value.components() {
        match component {
            Component::Normal(part) => {
                let text = part
                    .to_str()
                    .ok_or_else(|| anyhow::anyhow!("workspace paths must be UTF-8"))?;
                if text.contains(['/', '\\']) {
                    bail!("invalid workspace path component: {text}");
                }
                parts.push(text);
            }
            Component::CurDir => {}
            Component::ParentDir => bail!("workspace paths cannot contain '..'"),
            Component::Prefix(_) | Component::RootDir => {
                bail!("workspace paths must be relative")
            }
        }
    }
    if parts.is_empty() {
        bail!("workspace path cannot resolve to the root");
    }
    Ok(parts.join("/"))
}

pub fn native_path(root: &Path, normalized: &str) -> PathBuf {
    normalized
        .split('/')
        .fold(root.to_path_buf(), |path, part| path.join(part))
}

pub struct ScratchMatcher {
    rules: GlobSet,
}

impl ScratchMatcher {
    pub fn compile<'a>(patterns: impl IntoIterator<Item = &'a str>) -> Result<Self> {
        let mut builder = GlobSetBuilder::new();
        for pattern in patterns {
            let normalized = normalize_glob(pattern)?;
            add_glob(&mut builder, &normalized)?;
            if !has_glob_syntax(&normalized) {
                add_glob(&mut builder, &format!("{normalized}/**"))?;
            }
        }
        Ok(Self {
            rules: builder.build()?,
        })
    }

    pub fn matches(&self, normalized: &str) -> bool {
        self.rules.is_match(normalized)
    }
}

pub fn scratch_rules(paths: &[PathBuf]) -> Result<Vec<String>> {
    let mut rules = paths
        .iter()
        .map(|path| normalize_glob(&path.to_string_lossy()))
        .collect::<Result<Vec<_>>>()?;
    for segment in SCRATCH_SEGMENTS {
        rules.push(format!("**/{segment}"));
        rules.push(format!("**/{segment}/**"));
    }
    for prefix in [".reframe-memory*", ".reframe-workspace*"] {
        rules.push(format!("**/{prefix}"));
        rules.push(format!("**/{prefix}/**"));
    }
    rules.sort();
    rules.dedup();
    ScratchMatcher::compile(rules.iter().map(String::as_str))?;
    Ok(rules)
}

pub fn is_literal_rule(rule: &str) -> bool {
    !has_glob_syntax(rule)
}

fn normalize_glob(value: &str) -> Result<String> {
    let normalized = value.replace('\\', "/");
    if normalized.is_empty()
        || normalized.starts_with('/')
        || normalized.split('/').any(|part| part == "..")
        || normalized.contains(':')
    {
        bail!("scratch rule must be a contained relative glob: {value}");
    }
    Ok(normalized.trim_start_matches("./").to_owned())
}

fn add_glob(builder: &mut GlobSetBuilder, pattern: &str) -> Result<()> {
    let glob = GlobBuilder::new(pattern)
        .literal_separator(true)
        .backslash_escape(false)
        .case_insensitive(cfg!(windows))
        .build()?;
    builder.add(glob);
    Ok(())
}

fn has_glob_syntax(value: &str) -> bool {
    value.contains(['*', '?', '[', ']', '{', '}'])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paths_are_portable_and_contained() {
        assert_eq!(
            normalize_relative(Path::new("src/main.rs")).unwrap(),
            "src/main.rs"
        );
        assert!(normalize_relative(Path::new("../secret")).is_err());
        assert!(normalize_relative(Path::new("/rooted")).is_err());
    }

    #[test]
    fn scratch_matches_at_any_depth() {
        let rules = scratch_rules(&[PathBuf::from("generated/**")]).unwrap();
        let matcher = ScratchMatcher::compile(rules.iter().map(String::as_str)).unwrap();
        assert!(matcher.matches("web/node_modules/pkg/index.js"));
        assert!(matcher.matches("target/debug/tool"));
        assert!(matcher.matches("generated/report.txt"));
        assert!(!matcher.matches("src/targeting.rs"));
    }
}
