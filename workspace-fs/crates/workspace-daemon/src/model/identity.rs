use anyhow::{Result, bail};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceId(String);

impl WorkspaceId {
    pub fn parse(value: &str) -> Result<Self> {
        validate_identifier(value)?;
        Ok(Self(value.to_owned()))
    }

    pub fn generate() -> Self {
        Self(format!("task-{}", uuid::Uuid::new_v4()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn into_string(self) -> String {
        self.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ManifestId(String);

impl ManifestId {
    pub fn generate() -> Self {
        Self(format!("manifest-{}", uuid::Uuid::new_v4()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn into_string(self) -> String {
        self.0
    }
}

fn validate_identifier(value: &str) -> Result<()> {
    if value.is_empty()
        || value.len() > 96
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-_".contains(&byte))
    {
        bail!("ids may contain only ASCII letters, numbers, '-' and '_' (max 96)");
    }
    Ok(())
}
