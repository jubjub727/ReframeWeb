use anyhow::{Result, bail};
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeKind {
    Create,
    Write,
    Delete,
}

impl ChangeKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Create => "create",
            Self::Write => "write",
            Self::Delete => "delete",
        }
    }

    pub fn parse(value: &str) -> Result<Self> {
        match value {
            "create" => Ok(Self::Create),
            "write" => Ok(Self::Write),
            "delete" => Ok(Self::Delete),
            _ => bail!("invalid persisted change kind: {value}"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkspaceState {
    Active,
    Closed,
}

impl WorkspaceState {
    pub fn parse(value: &str) -> Result<Self> {
        match value {
            "active" => Ok(Self::Active),
            "closed" => Ok(Self::Closed),
            _ => bail!("invalid persisted workspace state: {value}"),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Change {
    pub path: String,
    pub kind: ChangeKind,
    pub size: Option<u64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn persisted_enums_reject_unknown_values() {
        assert!(ChangeKind::parse("renamed").is_err());
        assert!(WorkspaceState::parse("paused").is_err());
    }
}
